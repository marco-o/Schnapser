"""schnaps_web.game.player_one: one network as all four parts of the player."""

import jax
import pytest

from open_spiel.python.scale.ckpt import artifact
from open_spiel.python.scale.core import types
from open_spiel.python.scale.core import x64
from open_spiel.python.scale.envs import registry as env_registry
from open_spiel.python.scale.envs import schnaps_elena as elena
from open_spiel.python.scale.eval import match
from open_spiel.python.scale.policies import registry
from schnaps_web.game import player
from schnaps_web.game import player_one
from schnaps_web.tools import build_one

#: A tiny network that reads schnaps's InfoState (the parts' input).
NET = dict(
    arch_name="network",
    arch_kwargs=dict(
        encoder="schnaps_card_planes",
        game="schnaps",
        network=dict(
            chunk_size=None,
            compute_dtype="float32",
            policy_head=dict(kind="card_move_pointer"),
            torso=dict(
                attention="xla",
                center_keys=True,
                depth=1,
                embed_dim_per_head_over8=1,
                ff_factor=1,
                in_channels=70,
                kind="card_move_transformer",
                n_card=20,
                n_head=2,
                n_special_action=19,
                pos_emb_std=0.1,
            ),
            value_head=dict(
                init_scheme="torch_uniform", kind="scalar", source="value"
            ),
        ),
        num_actions=39,
        num_players=4,
        obs_format="schnaps_card_planes",
        obs_shape=[70, 20],
        value_layout="seat",
    ),
)


@pytest.fixture(scope="module")
def setup():
  x64.enable_x64()
  net = registry.build_part(NET)
  params = net.init_params(jax.random.key(3))
  env = env_registry.make("schnaps")
  return net, params, env


def test_it_plays_exactly_as_the_four_part_player(setup):
  net, params, env = setup
  four = player.SchnapsPlayerPolicy(
      parts={n: net for n in player.PART_NAMES}, rule="set_aware"
  )
  one = player_one.OneNetworkPlayerPolicy(net=net, rule="set_aware")
  ev = elena.evaluator(env)
  r = ev.head_to_head(
      match.Entrant("one", one, params, types.ARGMAX),
      match.Entrant(
          "four", four, {n: params for n in player.PART_NAMES}, types.ARGMAX
      ),
      16,
      jax.random.key(0),
  ).mean
  # Duplicate deals, greedy play: the same moves give exactly 0 every deal.
  assert r.mean == 0.0 and r.se == 0.0


def test_the_spec_records_one_network(setup):
  net, _, _ = setup
  one = player_one.OneNetworkPlayerPolicy(
      net=net, rule="set_aware", played_prior=0
  )
  kw = one.spec.arch_kwargs
  assert one.spec.arch_name == player_one.ARCH
  assert "parts" not in kw and kw["net"]["arch_name"] == "network"
  assert kw["played_prior"] == 0 and one.played is None
  rebuilt = registry.build(one.spec.arch_name, kw)
  assert isinstance(rebuilt, player_one.OneNetworkPlayerPolicy)
  assert rebuilt.spec == one.spec


def test_build_one_writes_a_player_that_loads(setup, tmp_path):
  net, params, env = setup
  src = tmp_path / "net"
  artifact.write_artifact(
      str(src),
      7,
      net,
      params,
      rules_sha=env.declared_rules_sha,
      env_spec=env_registry.spec_of(env).to_json(),
      env_name=env.name,
      extensions={"value_scale": 3.0},
  )
  out = tmp_path / "player"
  build_one.build(f"{src}@7", str(out), 2)
  art = artifact.load_artifact(str(out), 2)
  assert art.manifest.arch_name == player_one.ARCH
  assert art.manifest.extensions["value_scale"] == 3.0
  assert art.policy.rule.name == "set_aware"
  assert art.manifest.parents == (f"{artifact.norm_path(str(src))}@7",)
  with pytest.raises(ValueError, match="exists"):
    build_one.build(f"{src}@7", str(out), 2)
