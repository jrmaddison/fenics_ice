import numpy as np
from pathlib import Path
import h5py
from fenics import *
from fenics_ice import model
import argparse


def main(dd, infile, outfile, noise_sdev, L, seed=0):
    """
    Take velocity data from run_momsolve.py and add gaussian noise

    Expects an HDF5 file (containing both mesh & velocity function) as input
    """
    assert Path(infile).suffix == ".h5"
    assert Path(outfile).suffix == ".h5"
    assert L > 0.0
    assert noise_sdev > 0.0

    infile = HDF5File(MPI.comm_world, str(Path(dd)/infile), 'r')

    # Get mesh from file
    mesh = Mesh()
    infile.read(mesh, 'mesh', False)
    periodic_bc = bool(infile.attributes('mesh')['periodic'])

    if periodic_bc:
        V = VectorFunctionSpace(mesh,
                                'Lagrange',
                                1,
                                dim=2,
                                constrained_domain=model.PeriodicBoundary(L))

        # Create a non-periodic space for projection
        # (want to write out a non-periodic field)
        V_np = VectorFunctionSpace(mesh,
                                   'Lagrange',
                                   1,
                                   dim=2)

    else:
        V = VectorFunctionSpace(mesh,
                                'Lagrange',
                                1,
                                dim=2)

    # M = FunctionSpace(mesh, 'DG', 0)
    # Q = FunctionSpace(mesh, 'Lagrange', 1)

    # Read the velocity
    U = Function(V)
    infile.read(U, 'U')

    if(periodic_bc):
        U = project(U, V_np)

    uu, vv = U.split(True)

    u_array = uu.vector().get_local()
    v_array = vv.vector().get_local()

    np.random.seed(seed)
    u_noise = np.random.normal(scale=noise_sdev, size=u_array.size)
    v_noise = np.random.normal(scale=noise_sdev, size=v_array.size)

    u_array += u_noise
    v_array += v_noise

    # [::2] because tabulate_dof_coordinates produces two copies
    # (because 2 dofs per node...)
    x, y = np.hsplit(uu.function_space().tabulate_dof_coordinates(), 2)

    # Produce output as raw points & vel
    output = h5py.File(Path(dd)/outfile, 'w')

    output.create_dataset("x",
                          x.shape,
                          dtype=x.dtype,
                          data=x)

    output.create_dataset("y",
                          x.shape,
                          dtype=x.dtype,
                          data=y)

    output.create_dataset("u_obs",
                          x.shape,
                          dtype=np.float64,
                          data=u_array)

    output.create_dataset("v_obs",
                          x.shape,
                          dtype=np.float64,
                          data=v_array)

    noise_arr = np.zeros_like(x)
    noise_arr[:] = noise_sdev

    outfile.create_dataset("u_std",
                           x.shape,
                           dtype=np.float64,
                           data=noise_arr)

    outfile.create_dataset("v_std",
                           x.shape,
                           dtype=np.float64,
                           data=noise_arr)

    mask_arr = np.ones_like(x)

    outfile.create_dataset("mask_vel",
                           x.shape,
                           dtype=np.float64,
                           data=mask_arr)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--datadir', dest='dd', type=str,
                        required=True, help='Directory with input data')
    parser.add_argument('-i', '--infile', dest='infile', type=str,
                        required=True,
                        help='HDF5 File containing mesh & function')
    parser.add_argument('-o', '--outfile', dest='outfile', type=str,
                        required=True, help='Filename for HDF5 output')
    parser.add_argument('-s', '--sigma', dest='noise_sdev', type=float,
                        help='Standard deviation of added Gaussian Noise')
    parser.add_argument('-L', '--length', dest='L', type=int,
                        help='Length of IsmipC domain.')
    parser.add_argument('-r', '--seed', dest='seed', type=int,
                        help='Random seed for noise generation')

    parser.set_defaults(noise_sdev=1.0, L=False, seed=0)
    args = parser.parse_args()

    dd = args.dd
    infile = args.infile
    outfile = args.outfile
    noise_sdev = args.noise_sdev
    L = args.L
    seed = args.seed

    main(dd, infile, outfile, noise_sdev, L, seed)
