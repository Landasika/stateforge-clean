from stateforge.adapters.callable import CallableAdapter

from examples.m1_target import target


def build_adapter():
    return CallableAdapter(target)
