#!/usr/bin/env python
import sys

import os
import argparse
from fenics import *
from tlm_adjoint_fenics import *
import pickle
from IPython import embed

from fenics_ice import model, solver, prior, inout
from fenics_ice import mesh as fice_mesh
from fenics_ice.config import ConfigParser

import datetime
import numpy as np
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt

import slepc4py.SLEPc as SLEPc
import petsc4py.PETSc as PETSc

def run_eigendec(config_file):

    #Read run config file
    params = ConfigParser(config_file)
    log = inout.setup_logging(params)

    log.info("=======================================")
    log.info("=== RUNNING EIGENDECOMPOSITION PHASE ==")
    log.info("=======================================")

    inout.print_config(params)

    dd = params.io.input_dir
    outdir = params.io.output_dir

    #Ice only mesh
    mesh = Mesh(os.path.join(outdir,'mesh.xml'))

    #Set up Function spaces
    M = FunctionSpace(mesh,'DG',0)
    Q = FunctionSpace(mesh,'Lagrange',1)

    #Handle function with optional periodic boundary conditions
    if not params.mesh.periodic_bc:
       Qp = Q
       V = VectorFunctionSpace(mesh,'Lagrange',1,dim=2)
    else:
       Qp = fice_mesh.get_periodic_space(params, mesh, dim=1)
       V = fice_mesh.get_periodic_space(params, mesh, dim=2)

    #Load fields

    U = Function(V,os.path.join(outdir,'U.xml'))
    alpha = Function(Qp,os.path.join(outdir,'alpha.xml'))
    beta = Function(Qp,os.path.join(outdir,'beta.xml'))
    bed = Function(Q,os.path.join(outdir,'bed.xml'))


    thick = Function(M,os.path.join(outdir,'thick.xml'))
    mask = Function(M,os.path.join(outdir,'mask.xml'))
    mask_vel = Function(M,os.path.join(outdir,'mask_vel.xml'))
    u_obs = Function(M,os.path.join(outdir,'u_obs.xml'))
    v_obs = Function(M,os.path.join(outdir,'v_obs.xml'))
    u_std = Function(M,os.path.join(outdir,'u_std.xml'))
    v_std = Function(M,os.path.join(outdir,'v_std.xml'))
    uv_obs = Function(M,os.path.join(outdir,'uv_obs.xml'))
    Bglen = Function(M,os.path.join(outdir,'Bglen.xml'))

    bmelt = Function(M,os.path.join(outdir,'bmelt.xml'))
    smb = Function(M,os.path.join(outdir,'smb.xml'))

    #Initialize our model object
    mdl = model.model(mesh, mask, params)
    mdl.init_bed(bed)
    mdl.init_thick(thick)
    mdl.gen_surf()
    mdl.init_mask(mask)
    mdl.init_vel_obs(u_obs,v_obs,mask_vel,u_std,v_std)
    mdl.init_lat_dirichletbc()
    mdl.init_bmelt(bmelt)
    mdl.init_smb(smb)
    mdl.init_alpha(alpha)
    mdl.init_beta(beta, False)
    mdl.label_domain()

    #Setup our solver object
    slvr = solver.ssa_solver(mdl)

    cntrl = slvr.get_control()[0] #TODO generalise - get_control returns a list
    space = cntrl.function_space()

    msft_flag = params.eigendec.misfit_only
    if msft_flag:
        slvr.zero_inv_params()

    #Hessian Action
    slvr.set_hessian_action(cntrl)

    #Mass matrix solver
    xg,xb = Function(space), Function(space)
    test, trial = TestFunction(space), TrialFunction(space)
    mass = assemble(inner(test,trial)*slvr.dx)
    mass_solver = KrylovSolver("cg", "sor")
    mass_solver.parameters.update({"absolute_tolerance":1.0e-32,
                               "relative_tolerance":1.0e-14})
    mass_solver.set_operator(mass)

    #Regularization operator using inversion delta/gamma values
    #TODO - this won't handle dual inversion case
    if params.inversion.alpha_active:
        delta = params.inversion.delta_alpha
        gamma = params.inversion.gamma_alpha
    elif params.inversion.beta_active:
        delta = params.inversion.delta_beta
        gamma = params.inversion.gamma_beta

    reg_op = prior.laplacian(delta,gamma, space)

    #Counter for hessian action -- list rather than float/int necessary
    num_action_calls = [0]
    prior_action_calls = [0]
    # set_log_level(10)

    def ghep_action(x):
        """
        Hessian action w/o preconditioning
        """
        num_action_calls[0] += 1
        info("ghep_action call %i" % num_action_calls[0])
        _, _, ddJ_val = slvr.ddJ.action(cntrl, x)
        # reg_op.inv_action(ddJ_val.vector(), xg.vector()) <- gnhep_prior
        return function_get_values(ddJ_val)

    def prior_action(x):
        """
        Defines the action of the B matrix (prior)
        """
        prior_action_calls[0] += 1
        if prior_action_calls[0] % 10000 == 0:
            log.info("Prior action call %s" % prior_action_calls[0])
        reg_op.action(x.vector(), xg.vector())
        return function_get_values(xg)

    def prior_approx_action(x):
        """
        Only used for checking B' orthonormality
        """
        reg_op.approx_action(x.vector(), xg.vector())
        return function_get_values(xg)

    eps_error = [False]

    def flag_errors(fn):
        def wrapped_fn(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except:  # noqa: E722
                eps_error[0] = True
                raise
        return wrapped_fn


    class PythonMatrix:
        def __init__(self, action, X):
            self._action = action
            self._X = X

        @flag_errors
        def mult(self, A, x, y):
            function_set_values(self._X, x.getArray(readonly=True))
            y.setArray(self._action(self._X))


    def slepc_config_callback(config):
        log.info("Got to the callback")

        # st = config.getST()
        # st.setType('shift')

        ksp = config.getST().getKSP()
        # ksp.setType(PETSc.KSP.Type.GMRES)

        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(prior.LumpedPC(reg_op))

        # pc.setType(PETSc.PC.Type.NONE)

        #A_matrix already defined so just grab it
        A_matrix, _ = config.getOperators()

        #Equivalent code to tlm_adjoint for defining the shell matrix
        Y = space_new(space)
        n, N = function_local_size(Y), function_global_size(Y)
        B_matrix = PETSc.Mat().createPython(((n, N), (n, N)),
                                            PythonMatrix(prior_action, Y),
                                            comm=function_comm(Y))
        B_matrix.setUp()

        config.setOperators(A_matrix, B_matrix)

    # opts = {'prior': gnhep_prior_action, 'mass': gnhep_mass_action}
    # gnhep_func = opts[params.eigendec.precondition_by]

    num_eig = params.eigendec.num_eig
    n_iter = params.eigendec.power_iter #<- not used yet

    #Hessian eigendecomposition using SLEPSC
    eig_algo = params.eigendec.eig_algo
    if eig_algo == "slepc":

        #Eigendecomposition
        lam, vr = eigendecompose(space,
                                 ghep_action,
                                 tolerance = 1.0e-10,
                                 N_eigenvalues = num_eig,
                                 problem_type=SLEPc.EPS.ProblemType.GHEP,
                                 # solver_type=SLEPc.EPS.Type.ARNOLDI,
                                 configure=slepc_config_callback)


        # Check orthonormality of EVs

        if num_eig is not None and num_eig < 100:
            x = space_new(space)

            # Check for B (not B') orthogonality & normalisation
            for i in range(num_eig):
                reg_op.action(vr[i].vector(), xg.vector())
                norm = xg.vector().inner(Vector(vr[i].vector())) ** 0.5
                print("EV %s norm %s" % (i, norm))

            for i in range(num_eig):
                reg_op.action(vr[i].vector(), xg.vector())
                for j in range(i+1,num_eig):
                    inn = xg.vector().inner(Vector(vr[j].vector()))
                    print("EV %s %s inner %s" % (i, j, inn))

            # Check for B' orthogonality & normalisation
            for i in range(num_eig):
                reg_op.approx_action(vr[i].vector(), xg.vector())
                norm = xg.vector().inner(Vector(vr[i].vector())) ** 0.5
                print("EV %s approx norm %s" % (i,norm))

            for i in range(num_eig):
                reg_op.approx_action(vr[i].vector(), xg.vector())
                for j in range(i+1,num_eig):
                    inn = xg.vector().inner(Vector(vr[j].vector()))
                    print("EV %s %s approx inner %s" % (i,j, inn))


            embed()

        # TODO - multiply by \Theta here?
        # for v in vr:
        #     reg_op.approx_root_inv_action(v.vector(), x.vector())
        #     v.vector().set_local(x.vector().get_local())

        # for i in range(num_eig):
        #     print("EV %s norm %s" % (i, np.inner(prior_action(vr[i]), vr[i].vector())))

        # for i in range(num_eig):
        #     for j in range(i+1,num_eig):
        #         print("EV %s %s inner %s" % (i, j, np.inner(prior_action(vr[i]),
        #                      vr[j].vector())))


        # Uses extreme amounts of disk space; suitable for ismipc only
        # #Save eigenfunctions
        # vtkfile = File(os.path.join(outdir,'vr.pvd'))
        # for v in vr:
        #     v.rename('v', v.label())
        #     vtkfile << v
        #
        # vtkfile = File(os.path.join(outdir,'vi.pvd'))
        # for v in vi:
        #     v.rename('v', v.label())
        #     vtkfile << v

        hdf5file = HDF5File(slvr.mesh.mpi_comm(), os.path.join(outdir, 'vr.h5'), 'w')
        for i, v in enumerate(vr): hdf5file.write(v, 'v', i)

    else:
        raise NotImplementedError

    #Save eigenvals and some associated info
    fileout = params.io.eigenvalue_file
    pfile = open( os.path.join(outdir, fileout), "wb" )
    pickle.dump( [lam, num_eig, n_iter, eig_algo, msft_flag, outdir, dd], pfile)
    pfile.close()

    #Plot of eigenvals
    lamr = lam.real
    lpos = np.argwhere(lamr > 0)
    lneg = np.argwhere(lamr < 0)
    lind = np.arange(0,len(lamr))
    plt.semilogy(lind[lpos], lamr[lpos], '.')
    plt.semilogy(lind[lneg], np.abs(lamr[lneg]), '.')
    plt.savefig(os.path.join(outdir,'lambda.pdf'))

    #Note - for now this does nothing, but eventually if the whole series
    #of runs were done without re-initializing solver, it'd be important to
    #put the inversion params back
    if msft_flag:
        slvr.set_inv_params()

if __name__ == "__main__":
    stop_annotating()

    assert len(sys.argv) == 2, "Expected a configuration file (*.toml)"
    run_eigendec(sys.argv[1])
