"""Module-level reduce/combine/empty for probe_opt0_pickle_rv3 (pickled by reference)."""


def reduce(values):
    return len(values)


def combine(a, b):
    return a + b


def empty():
    return 0
