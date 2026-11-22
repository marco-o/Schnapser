"""A full schnaps player built from ONE network that plays every contract.

Step 2a of Docker/gpu-training.md trains one network on schnaps_mixed
(Normal deals and the forced Schnapser, Lomt and Bauern deals). The
contract is in the InfoState the network reads, so the same network serves
as all four parts of game/player.SchnapsPlayerPolicy. This class is that
player, evaluating the network once per row instead of once per part:

  policy = OneNetworkPlayerPolicy(net=net, rule="set_aware", value_scale=3.0)
  params = net_params        # one network's params, not a dict of four

It plays exactly as SchnapsPlayerPolicy(parts={every part: net}) with the
same params in every part (tests/test_player_one.py checks this): the trump
choice, the bidding (rule, hard rules, played-results blend) and the routing
are the parent's code. Only the network calls are shared:

* evaluate: the parent asks each part to evaluate the same row; the parts
  are one _SharedPart that runs the network once per (params, carry, step,
  key) and hands back the same output to the other three.
* value_fn: the bidding asks for a contract's value on an InfoState whose
  contract is already that contract, so one network call answers for any
  contract.

Registered as "schnaps_web.player_one" (tools/build_one.py writes one).
"""

import dataclasses
from typing import Any, Mapping, Optional, Union

import jax.numpy as jnp

from open_spiel.python.scale.core import types
from open_spiel.python.scale.policies import registry
from schnaps_web.game import player

ARCH = "schnaps_web.player_one"
PART_NAMES = player.PART_NAMES


class _SharedPart:
  """One network seen as several parts: repeated calls reuse one output.

  Only `evaluate` is cached, by the identity of its arguments (the parent
  passes the very same objects to every part). The last arguments are kept,
  so their ids cannot be reused by new objects while cached.
  """

  def __init__(self, net: types.Policy):
    self.net = net
    self._last = None

  def __getattr__(self, name):
    return getattr(self.net, name)

  def evaluate(self, params, carry, step, key):
    args = (params, carry, step, key)
    if self._last is not None and all(
        a is b for a, b in zip(self._last[0], args)
    ):
      return self._last[1]
    out = self.net.evaluate(params, carry, step, key)
    self._last = (args, out)
    return out


class OneNetworkPlayerPolicy(player.SchnapsPlayerPolicy):
  """The one-network player (module doc).

  Attributes:
    net: the network's Policy.
    (the rest as SchnapsPlayerPolicy)
  """

  def __init__(
      self,
      net: Union[types.Policy, Mapping[str, Any]],
      rule: str = "greedy",
      rule_kwargs: Optional[Mapping[str, Any]] = None,
      value_scale: float = 3.0,
      played_prior: Optional[float] = None,
  ):
    net = registry.build_part(net)
    super().__init__(
        parts={n: net for n in PART_NAMES},
        rule=rule,
        rule_kwargs=rule_kwargs,
        value_scale=value_scale,
        played_prior=played_prior,
    )
    self.net = net
    shared = _SharedPart(net)
    self.parts = {n: shared for n in PART_NAMES}
    kw = dict(self.spec.arch_kwargs)
    kw.pop("parts")
    kw["net"] = dict(
        arch_name=net.spec.arch_name, arch_kwargs=dict(net.spec.arch_kwargs)
    )
    self.spec = dataclasses.replace(self.spec, arch_name=ARCH, arch_kwargs=kw)

  def _fan(self, x):
    """The parent's per-part dict, every part holding the same object."""
    return {n: x for n in PART_NAMES}

  def init_params(self, key=None):
    return self.net.init_params(key)

  def init_carry(self, params, batch, seat, key):
    return self.net.init_carry(params, batch, seat, key)

  def observe(self, params, carry, step):
    return self.net.observe(params, carry, step)

  def value_fn(self, params, carry, step, key):
    """The parent's ValueFn with one network call per InfoState.

    Called by the parent's evaluate with the fanned dicts (any part's entry
    is the network's).
    """
    p, c = params[PART_NAMES[0]], carry[PART_NAMES[0]]
    seat = jnp.asarray(step.seat, jnp.int32)

    def value_fn(info, contract):
      # The contract is in the InfoState already and the parent only picks
      # which part reads it; every part is this network, so it is not needed.
      del contract
      out = self.net.evaluate(p, c, step._replace(info=info), key)
      return self._seat_value(out, seat)

    return value_fn

  def evaluate(self, params, carry, step, key):
    return super().evaluate(self._fan(params), self._fan(carry), step, key)


registry.register(ARCH, OneNetworkPlayerPolicy)
