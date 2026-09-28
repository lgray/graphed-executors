"""A tritonclient-shaped fake: records connections and infer calls per process."""
import numpy as np

CONNECTS: list[str] = []
INFERS: list[tuple[str, int]] = []


class InferInput:
    def __init__(self, name, shape, dtype):
        self.name, self.shape = name, shape

    def set_data_from_numpy(self, x):
        self.x = np.asarray(x, dtype="float32")


class InferRequestedOutput:
    def __init__(self, name):
        self.name = name


class _Result:
    def __init__(self, y, name):
        self.y, self.name = y, name

    def as_numpy(self, name):
        return self.y


class _Client:
    def __init__(self, url):
        self.url = url

    def infer(self, model, inputs, outputs):
        x = inputs[0].x
        INFERS.append((self.url, len(x)))
        return _Result(x.reshape(len(x), -1)[:, 0] * 0.5, outputs[0].name)

    def close(self):
        pass


def transport(params):
    CONNECTS.append(str(params["url"]))
    return _Client(str(params["url"]))
