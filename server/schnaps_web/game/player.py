# Copyright 2026 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A full schnaps player built from one network per contract.

Copied for schnaps-web from open_spiel/python/scale/envs/schnaps_player.py,
registered as "schnaps_web.player" (so it cannot clash with the original).

SchnapsPlayerPolicy (arch "schnaps.player") plays schnaps(max_flecks=2)
with four card-play networks and a bid rule (envs.schnaps_bidding):

* the trump choice: the Normal network (trained on schnaps_normal);
* the bidding: the rule, on estimates from the four networks' value heads
  (schnaps_bidding.estimate);
* the play: the network of the contract being played: Normal, or the
  forced-contract network of Schnapser, Lomt or Bauern
  (envs.schnaps_forced), for the declarer and the defenders alike.

  policy = SchnapsPlayerPolicy(
      parts={"normal": net, "schnapser": s, "lomt": l, "bauern": b},
      rule="greedy", rule_kwargs={"margin": 0.0}, value_scale=3.0,
      played_prior=None)
  params = {"normal": pn, "schnapser": ps, "lomt": pl, "bauern": pb}

schnaps-web: the parts may be different networks (the large player pairs
a bigger Normal network with the compact forced-contract ones); only the
aux keys all parts share are routed.

The parts must read the same InfoState (envs.schnaps) and be stateless
in-graph JAX policies; they are nested in arch_kwargs as {"arch_name",
"arch_kwargs"} records, so the registry rebuilds the whole player from an
artifact (examples/schnaps_build_player.py writes one). value_scale is the
factor from a network's value to game points (the networks trained on
points / 3).

played_prior: the bid estimates are moved toward the played results of
the bidding module's table (bidding, "Played results"), the network
counting as `played_prior` deals; None means bidding.PLAYED_PRIOR, and 0
turns it off (as it is off when the table file is missing). It is recorded
in arch_kwargs only when given, so artifacts built before it rebuild
unchanged (and use the table).

Every part is evaluated on every row (simple, not fast). Outputs:
logits and aux of the routed part (aux also carries "bid_value",
f32[B, 39], the estimates on bidding rows, -inf elsewhere); on bidding rows
the logits are one-hot on the chosen bid and the value is its estimate.
"""

from typing import Any, Mapping, Optional, Union

import jax
import jax.numpy as jnp

from open_spiel.python.jax.games import schnaps as game
from open_spiel.python.scale.core import types
from open_spiel.python.scale.envs import schnaps
from schnaps_web.game import bidding
from open_spiel.python.scale.policies import fixed_action
from open_spiel.python.scale.policies import registry

ARCH = "schnaps_web.player"
#: The parts, in contract order (index = contract id).
PART_NAMES = ("normal", "schnapser", "lomt", "bauern")


def _select(cond, a, b):
  """`a` where cond[B], else `b`, broadcast over trailing axes."""
  cond = jnp.reshape(cond, cond.shape + (1,) * (jnp.ndim(a) - cond.ndim))
  return jnp.where(cond, a, b)


class SchnapsPlayerPolicy(types.Policy):
  """The full player (module doc).

  Attributes:
    parts: {name: Policy}, PART_NAMES.
    rule: the BidRule.
    value_scale: network value -> game points.
    spec: the PolicySpec.
  """

  def __init__(
      self,
      parts: Mapping[str, Union[types.Policy, Mapping[str, Any]]],
      rule: str = "greedy",
      rule_kwargs: Optional[Mapping[str, Any]] = None,
      value_scale: float = 3.0,
      played_prior: Optional[float] = None,
  ):
    if set(parts) != set(PART_NAMES):
      raise ValueError(f"parts must be {PART_NAMES}, got {sorted(parts)}")
    self.parts = {n: registry.build_part(parts[n]) for n in PART_NAMES}
    for n, p in self.parts.items():
      s = p.spec
      if s.stateful or s.capability != types.Capability.NATIVE_JAX:
        raise ValueError(
            f"part {n} must be a stateless NATIVE_JAX policy, got "
            f"stateful={s.stateful}, {s.capability.value}"
        )
      if (s.num_actions, s.num_players) != (
          schnaps.NUM_ACTIONS,
          schnaps.NUM_PLAYERS,
      ):
        raise ValueError(f"part {n} does not play schnaps: {s}")
    rule_kwargs = dict(rule_kwargs or {})
    self.rule = bidding.make_rule(rule, rule_kwargs)
    self.value_scale = float(value_scale)
    self.played_prior = (
        bidding.PLAYED_PRIOR if played_prior is None else float(played_prior)
    )
    if self.played_prior < 0:
      raise ValueError(f"played_prior must be >= 0, got {played_prior}")
    self.played = (
        bidding.load_played_table() if self.played_prior > 0 else None
    )
    extra = {} if played_prior is None else {"played_prior": played_prior}
    normal = self.parts["normal"].spec
    self.spec = types.PolicySpec(
        game=schnaps.SchnapsEnv.name,
        obs_format=normal.obs_format,
        num_actions=schnaps.NUM_ACTIONS,
        num_players=schnaps.NUM_PLAYERS,
        stateful=False,
        capability=types.Capability.NATIVE_JAX,
        framework="jax",
        arch_name=ARCH,
        arch_kwargs=dict(
            parts={
                n: dict(
                    arch_name=p.spec.arch_name,
                    arch_kwargs=dict(p.spec.arch_kwargs),
                )
                for n, p in self.parts.items()
            },
            rule=rule,
            rule_kwargs=rule_kwargs,
            value_scale=value_scale,
            **extra,
        ),
    )

  def init_params(self, key=None):
    key = jax.random.key(0) if key is None else key
    keys = jax.random.split(key, len(PART_NAMES))
    return {
        n: self.parts[n].init_params(k) for n, k in zip(PART_NAMES, keys)
    }

  def encode(self, info):
    return self.parts["normal"].encode(info)

  def init_carry(self, params, batch, seat, key):
    return {
        n: self.parts[n].init_carry(params[n], batch, seat, key)
        for n in PART_NAMES
    }

  def observe(self, params, carry, step):
    return {
        n: self.parts[n].observe(params[n], carry[n], step) for n in PART_NAMES
    }

  def _seat_value(self, out, seat):
    """The value of each row's own seat, in game points."""
    v = jnp.take_along_axis(out.value, seat[:, None], axis=1)[:, 0]
    return v * self.value_scale

  def value_fn(self, params, carry, step, key) -> bidding.ValueFn:
    """The ValueFn of these params: each part's value head on an InfoState.

    Args:
      params: the params.
      carry: the carry.
      step: the SeatStep whose seats view the InfoStates.
      key: the evaluate key.

    Returns:
      value_fn(info, contract) -> f32[B] game points for the viewer's pair.
    """
    seat = jnp.asarray(step.seat, jnp.int32)

    def part_value(n, info):
      out = self.parts[n].evaluate(
          params[n], carry[n], step._replace(info=info), key
      )
      return self._seat_value(out, seat)

    def value_fn(info, contract):
      if isinstance(contract, int):
        return part_value(PART_NAMES[contract], info)
      vals = jnp.stack([part_value(n, info) for n in PART_NAMES], axis=1)
      c = jnp.clip(jnp.asarray(contract, jnp.int32), 0, len(PART_NAMES) - 1)
      return jnp.take_along_axis(vals, c[:, None], axis=1)[:, 0]

    return value_fn

  def evaluate(self, params, carry, step, key):
    info = step.info
    seat = jnp.asarray(step.seat, jnp.int32)
    outs = [
        self.parts[n].evaluate(params[n], carry[n], step, key)
        for n in PART_NAMES
    ]
    phase = jnp.asarray(info["phase"], jnp.int32)
    contract = jnp.clip(
        jnp.asarray(info["contract"], jnp.int32), 0, len(PART_NAMES) - 1
    )
    contract = jnp.where(phase == game.PHASE_PLAY, contract, game.NORMAL)
    # The parts may differ in their aux heads (the large player's Normal
    # network has two): only the aux keys every part has are routed.
    common = sorted(set.intersection(*(set(o.aux) for o in outs)))
    outs = [
        types.PolicyOutput(
            logits=o.logits, value=o.value, aux={k: o.aux[k] for k in common}
        )
        for o in outs
    ]
    routed = outs[0]
    for c in range(1, len(PART_NAMES)):
      routed = jax.tree.map(
          lambda a, b, c=c: _select(contract == c, a, b), outs[c], routed
      )

    # The hard rules (bidding.allowed_bids) hold whatever the rule.
    legal = bidding.allowed_bids(info, step.legal_mask)
    est = bidding.estimate(
        info,
        legal,
        self.value_fn(params, carry, step, key),
        self.played,
        max(self.played_prior, 1e-9),
    )
    ctx = bidding.BidContext(
        info=info,
        legal=legal,
        estimates=est,
        set=bidding.set_context(info),
    )
    is_bid = phase == game.PHASE_BIDDING
    bid = self.rule.choose(ctx, key)
    hot = fixed_action.one_hot_output(
        bid, is_bid, schnaps.NUM_ACTIONS, schnaps.NUM_PLAYERS
    )
    chosen = jnp.take_along_axis(est.value, bid[:, None], axis=1)[:, 0]
    bid_value = (
        jax.nn.one_hot(seat, schnaps.NUM_PLAYERS, dtype=jnp.float32)
        * (chosen / self.value_scale)[:, None]
    )
    logits = _select(is_bid, hot.logits, routed.logits)
    value = _select(is_bid, bid_value, routed.value)
    aux = dict(routed.aux)
    aux["bid_value"] = jnp.where(is_bid[:, None], est.value, -jnp.inf)
    return types.PolicyOutput(logits=logits, value=value, aux=aux)


registry.register(ARCH, SchnapsPlayerPolicy)
