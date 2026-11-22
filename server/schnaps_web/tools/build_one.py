r"""Writes a one-network player (schnaps_web.game.player_one) as an artifact.

The network is a step-2a checkpoint trained on schnaps_mixed (one network
for every contract, Docker/step2a-options.md). It reads schnaps's InfoState,
so it plays the full game as all four parts of the site player, with the
same bid rule as the Basic and Large players:

  python -m schnaps_web.tools.build_one ~/schnaps_mixed_big_gpu@500 \
      --out_dir ~/schnaps_mixed_player --step 500

The player is written to --out_dir/<--step> for schnaps(max_flecks=2), with
the checkpoint as its parent. An existing step is replaced only with
--overwrite.
"""

import argparse
import os
import shutil
import sys

from open_spiel.python.scale.ckpt import artifact
from open_spiel.python.scale.core import x64
from open_spiel.python.scale.envs import registry as env_registry
from schnaps_web.game import bidding
from schnaps_web.game import player_one


def build(
    source: str,
    out_dir: str,
    step: int,
    rule: str = "set_aware",
    rule_kwargs=None,
    overwrite: bool = False,
) -> str:
  """Writes the player (module doc).

  Args:
    source: the network, "<dir>@<step>".
    out_dir: the output dir.
    step: the output step.
    rule: the bid rule.
    rule_kwargs: its kwargs.
    overwrite: replace an existing step.

  Returns:
    The artifact id.

  Raises:
    ValueError: the step exists and overwrite is off.
  """
  rule_kwargs = dict(rule_kwargs or {})
  out_dir = os.path.expanduser(out_dir)
  if artifact.exists(out_dir, step):
    if not overwrite:
      raise ValueError(f"{out_dir}@{step} exists (use --overwrite)")
    shutil.rmtree(os.path.join(out_dir, str(step)))
  path, src_step = source.rsplit("@", 1)
  path = os.path.expanduser(path)
  src_id = f"{artifact.norm_path(path)}@{src_step}"
  net = artifact.load_artifact(path, int(src_step))
  value_scale = float(net.manifest.extensions.get("value_scale", 1.0))
  policy = player_one.OneNetworkPlayerPolicy(
      net=net.policy,
      rule=rule,
      rule_kwargs=rule_kwargs,
      value_scale=value_scale,
  )
  env = env_registry.make("schnaps")
  artifact.write_artifact(
      out_dir,
      step,
      policy,
      net.params,
      rules_sha=env.declared_rules_sha,
      env_spec=env_registry.spec_of(env).to_json(),
      default_rule=net.manifest.default_rule,
      env_name=env.name,
      parents=(src_id,),
      lineage=artifact.lineage(
          src_id, net.manifest.step, rule=rule, rule_kwargs=rule_kwargs
      ),
      extensions={"value_scale": value_scale},
  )
  out = f"{artifact.norm_path(out_dir)}@{step}"
  print(f"wrote {out}: rule {rule} {rule_kwargs}, network {src_id}")
  return out


def main(argv=None) -> None:
  p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
  p.add_argument("source", help="the network checkpoint, <dir>@<step>")
  p.add_argument("--out_dir", default="~/schnaps_mixed_player")
  p.add_argument("--step", type=int, default=0)
  p.add_argument(
      "--rule", default="set_aware", choices=bidding.registered_rules()
  )
  p.add_argument("--overwrite", action="store_true")
  a = p.parse_args(argv)
  x64.enable_x64()
  try:
    build(a.source, a.out_dir, a.step, a.rule, overwrite=a.overwrite)
  except ValueError as e:
    sys.exit(str(e))


if __name__ == "__main__":
  main()
