# For fenics_ice copyright information see ACKNOWLEDGEMENTS in the fenics_ice
# root directory

# This file is part of fenics_ice.
#
# fenics_ice is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# fenics_ice is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with tlm_adjoint.  If not, see <https://www.gnu.org/licenses/>.

import pytest
import numpy as np
from runs import run_inv, run_forward, run_eigendec, run_errorprop, run_invsigma
from tlm_adjoint.fenics import *
from fenics import norm
from fenics_ice import config
from pathlib import Path
from mpi4py import MPI

def EQReset():
    """Take care of tlm_adjoint EquationManager"""
    # This prevents checkpointing errors when these run phases
    # are tested after the stuff in test_model.py
    reset_manager("memory")
    clear_caches()
    stop_manager()

@pytest.mark.order(1)
@pytest.mark.dependency()
def test_run_inversion(persistent_temp_model, monkeypatch):

    work_dir = persistent_temp_model["work_dir"]
    toml_file = persistent_temp_model["toml_filename"]

    # Switch to the working directory
    monkeypatch.chdir(work_dir)

    # Get expected values from the toml file
    params = config.ConfigParser(toml_file, top_dir=work_dir)
    expected_cntrl_norm = params.testing.expected_cntrl_norm
    expected_J_inv = params.testing.expected_J_inv

    EQReset()

    # Run the thing
    mdl_out = run_inv.run_inv(toml_file)

    cntrl = mdl_out.solvers[0].get_control()[0]
    cntrl_norm = norm(cntrl.vector())

    J_inv = mdl_out.solvers[0].J_inv.value()

    pytest.check_float_result(cntrl_norm,
                              expected_cntrl_norm,
                              work_dir, 'expected_cntrl_norm')

    pytest.check_float_result(J_inv,
                              expected_J_inv,
                              work_dir, 'expected_J_inv')

@pytest.mark.tv
def test_tv_run_inversion(persistent_temp_model, monkeypatch):
    """
    Taylor verification of inverse model
    """
    work_dir = persistent_temp_model["work_dir"]
    toml_file = persistent_temp_model["toml_filename"]

    # Switch to the working directory
    monkeypatch.chdir(work_dir)

    EQReset()

    # Run the thing
    mdl_out = run_inv.run_inv(toml_file)

    # Get expected values from the toml file
    alpha_active = mdl_out.params.inversion.alpha_active
    beta_active = mdl_out.params.inversion.beta_active

    if alpha_active:

        fwd_alpha = mdl_out.solvers[0].forward
        alpha = mdl_out.solvers[0].alpha

        min_order = taylor_test_tlm(fwd_alpha,
                                    alpha,
                                    tlm_order=1,
                                    seed=1.0e-5)
        assert(min_order > 1.95)

        min_order = taylor_test_tlm_adjoint(fwd_alpha,
                                            alpha,
                                            adjoint_order=1,
                                            seed=1.0e-5)
        assert(min_order > 1.95)

        min_order = taylor_test_tlm_adjoint(fwd_alpha,
                                            alpha,
                                            adjoint_order=2,
                                            seed=1.0e-5)
        assert(min_order > 1.95)

    if beta_active:

        fwd_beta = mdl_out.solvers[0].forward
        beta = mdl_out.solvers[0].beta

        min_order = taylor_test_tlm(fwd_beta,
                                    beta,
                                    tlm_order=1,
                                    seed=1.0e-5)
        assert(min_order > 1.95)

        min_order = taylor_test_tlm_adjoint(fwd_beta,
                                            beta,
                                            adjoint_order=1,
                                            seed=1.0e-5)
        assert(min_order > 1.95)

        min_order = taylor_test_tlm_adjoint(fwd_beta,
                                            beta,
                                            adjoint_order=2,
                                            seed=1.0e-5)
        assert(min_order > 1.95)

@pytest.mark.order(2)
@pytest.mark.dependency(["test_run_inversion"])
def test_run_forward(existing_temp_model, monkeypatch, setup_deps, request):

    #setup_deps.set_case_dependency(request, ["test_run_inversion"])

    work_dir = existing_temp_model["work_dir"]
    toml_file = existing_temp_model["toml_filename"]

    # Switch to the working directory
    monkeypatch.chdir(work_dir)

    # Get expected values from the toml file
    params = config.ConfigParser(toml_file, top_dir=work_dir)
    expected_delta_qoi = params.testing.expected_delta_qoi
    expected_u_norm = params.testing.expected_u_norm

    EQReset()

    mdl_out = run_forward.run_forward(toml_file)

    # from fenics_ice import graphviz
    # manager_graph = graphviz.dot()
    # with open("forward_manager.dot", "w") as outfile:
    #     outfile.write(manager_graph)

    slvr = mdl_out.solvers[0]

    delta_qoi = slvr.Qval_ts[-1] - slvr.Qval_ts[0]
    u_norm = norm(slvr.U)

    pytest.check_float_result(delta_qoi,
                              expected_delta_qoi,
                              work_dir, 'expected_delta_qoi', tol=1.0e-5)

    pytest.check_float_result(u_norm,
                              expected_u_norm,
                              work_dir, 'expected_u_norm', tol=1.0e-5)

@pytest.mark.tv
def test_tv_run_forward(existing_temp_model, monkeypatch, setup_deps, request):
    """
    Taylor verification of the forward timestepping model
    """

    work_dir = existing_temp_model["work_dir"]
    toml_file = existing_temp_model["toml_filename"]

    # Switch to the working directory
    monkeypatch.chdir(work_dir)
    EQReset()

    mdl_out = run_forward.run_forward(toml_file)

    # from fenics_ice import graphviz
    # manager_graph = graphviz.dot()
    # with open("forward_manager.dot", "w") as outfile:
    #     outfile.write(manager_graph)

    slvr = mdl_out.solvers[0]

    qoi_func = slvr.get_qoi_func()
    cntrl = slvr.get_control()

    slvr.reset_ts_zero()
    J = slvr.timestep(adjoint_flag=1, qoi_func=qoi_func)[0]
    dJ = compute_gradient(J, cntrl)

    def forward_ts(cntrl, cntrl_init, name):
        slvr.reset_ts_zero()
        if(name == 'alpha'):
            slvr._alpha = cntrl
        elif(name == 'beta'):
            slvr._beta = cntrl
        else:
            raise ValueError(f"Unrecognised cntrl name: {name}")

        result = slvr.timestep(adjoint_flag=1, qoi_func=slvr.get_qoi_func())[0]

        # Reset after simulation - confirmed necessary
        if(name == 'alpha'):
            slvr._alpha = cntrl_init
        elif(name == 'beta'):
            slvr._beta = cntrl_init
        else:
            raise ValueError(f"Bad control name {name}")

        return result

    cntrl_init = [f.copy(deepcopy=True) for f in cntrl]

    seeds = {'alpha': 1e-2, 'beta': 1e-1}

    for cntrl_curr, cntrl_curr_init, dJ_curr in zip(cntrl, cntrl_init, dJ):

        min_order = taylor_test(lambda cntrl_val: forward_ts(cntrl_val,
                                                             cntrl_curr_init,
                                                             cntrl_curr.name()),
                                cntrl_curr,
                                J_val=J.value(),
                                dJ=dJ_curr,
                                seed=seeds[cntrl_curr.name()],
                                M0=cntrl_curr_init,
                                size=6)

        print(f"Forward simulation cntrl: {cntrl_curr.name()} min_order: {min_order}")
        assert(min_order > 1.95)


@pytest.mark.order(3)
@pytest.mark.dependency(['test_run_forward'], ['test_run_inversion'])
def test_run_eigendec(existing_temp_model, monkeypatch, setup_deps, request):

    #setup_deps.set_case_dependency(request, ["test_run_inversion"])

    work_dir = existing_temp_model["work_dir"]
    toml_file = existing_temp_model["toml_filename"]

    # Switch to the working directory
    monkeypatch.chdir(work_dir)

    # Get expected values from the toml file
    params = config.ConfigParser(toml_file, top_dir=work_dir)
    expected_evals_sum = params.testing.expected_evals_sum
    expected_evec0_norm = params.testing.expected_evec0_norm

    EQReset()

    mdl_out = run_eigendec.run_eigendec(toml_file)

    slvr = mdl_out.solvers[0]

    evals_sum = np.sum(slvr.eigenvals)
    evec0_norm = norm(slvr.eigenfuncs[0])

    tol = 1e-5

    pytest.check_float_result(evals_sum,
                              expected_evals_sum,
                              work_dir, 'expected_evals_sum', tol=tol)
    pytest.check_float_result(evec0_norm,
                              expected_evec0_norm,
                              work_dir, 'expected_evec0_norm', tol=tol)

@pytest.mark.order(4)
@pytest.mark.dependency(["test_run_eigendec", "test_run_forward"])
def test_run_errorprop(existing_temp_model, monkeypatch, setup_deps, request):

    #setup_deps.set_case_dependency(request, ["test_run_eigendec", "test_run_forward"])

    work_dir = existing_temp_model["work_dir"]
    toml_file = existing_temp_model["toml_filename"]

    # Switch to the working directory
    monkeypatch.chdir(work_dir)

    # Get expected values from the toml file
    params = config.ConfigParser(toml_file, top_dir=work_dir)
    expected_Q_sigma = params.testing.expected_Q_sigma
    expected_Q_sigma_prior = params.testing.expected_Q_sigma_prior

    EQReset()

    mdl_out = run_errorprop.run_errorprop(toml_file)

    Q_sigma = mdl_out.Q_sigma[-1]
    Q_sigma_prior = mdl_out.Q_sigma_prior[-1]

    if pytest.parallel:
        tol = 5e-5

    else:
        tol = 1e-5

    pytest.check_float_result(Q_sigma,
                              expected_Q_sigma,
                              work_dir,
                              'expected_Q_sigma', tol=tol)
    pytest.check_float_result(Q_sigma_prior,
                              expected_Q_sigma_prior,
                              work_dir,
                              'expected_Q_sigma_prior', tol=tol)

@pytest.mark.skipif(pytest.parallel, reason='broken in parallel')
@pytest.mark.dependency(["test_run_eigendec"],["test_run_errorprop"])
def test_run_invsigma(existing_temp_model, monkeypatch, setup_deps, request):

    #setup_deps.set_case_dependency(request, ["test_run_eigendec"])

    work_dir = existing_temp_model["work_dir"]
    toml_file = existing_temp_model["toml_filename"]

    # Switch to the working directory
    monkeypatch.chdir(work_dir)

    # Get expected values from the toml file
    params = config.ConfigParser(toml_file, top_dir=work_dir)
    expected_cntrl_sigma_norm = params.testing.expected_cntrl_sigma_norm
    expected_cntrl_sigma_prior_norm = params.testing.expected_cntrl_sigma_prior_norm

    EQReset()

    mdl_out = run_invsigma.run_invsigma(toml_file)

    cntrl_sigma_norm = sum([norm(sig) for sig in mdl_out.cntrl_sigma])
    cntrl_sigma_prior_norm = sum([norm(sig) for sig in mdl_out.cntrl_sigma_prior])

    if pytest.parallel:
        tol = 1e-5
    else:
        tol = 1e-5

    pytest.check_float_result(cntrl_sigma_norm,
                              expected_cntrl_sigma_norm,
                              work_dir,
                              "expected_cntrl_sigma_norm", tol=tol)

    pytest.check_float_result(cntrl_sigma_prior_norm,
                              expected_cntrl_sigma_prior_norm,
                              work_dir,
                              "expected_cntrl_sigma_prior_norm", tol=tol)
