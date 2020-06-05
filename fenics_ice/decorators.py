"""
Decorator library - TODO should this be merged with something else?
"""

import logging
import functools
import time

class count_calls:  # noqa: N801
    """
    Decorator to count function calls

    Log interval can be set, e.g. @count_calls(1000)
    """

    def __init__(self, interval=1, fn_name=None):
        """Initialize counter, logger and logging interval"""
        self.n = 0
        self.interval = interval
        self.log = logging.getLogger("fenics_ice")
        self.fn_name = fn_name

    def __call__(self, f):
        """Return wrapped function"""
        def wrapped(*args, **kwargs):
            self.n += 1
            if(self.n % self.interval == 0):
                name = self.fn_name if self.fn_name is not None else f.__name__
                self.log.info("%s call %s" % (name, self.n))
            return f(*args, **kwargs)

        return wrapped


def flag_errors(fn):
    """
    Catch errors from SLEPc/PETSc

    Copied from tlm_adjoint eigendecomposition.py. Not sure this
    will work as intended, because eps_error is defined in this
    decorator, whereas in tlm_adjoint it's in the main scope.
    """
    eps_error = [False]

    def wrapped_fn(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except:  # noqa: E722
            eps_error[0] = True
            raise
    return wrapped_fn

def timer(func):
    """Print the runtime of the decorated function"""

    @functools.wraps(func)
    def wrapper_timer(*args, **kwargs):
        start_time = time.perf_counter()
        value = func(*args, **kwargs)
        end_time = time.perf_counter()
        run_time = end_time - start_time
        print(f"Finished {func.__name__!r} in {run_time:.4f} secs")
        return value

    return wrapper_timer