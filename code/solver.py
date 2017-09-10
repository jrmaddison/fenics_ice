from dolfin import *
import numpy as np
import timeit
from IPython import embed


class ssa_solver:

    def __init__(self, model):
        self.model = model

        #Finite Elements


        #Fields
        surf = model.surf
        bed = model.bed
        height = model.thick
        mask = model.mask
        B2 = model.bdrag
        bmelt = model.bmelt

        #Constants
        rhoi = model.rhoi
        rhow = model.rhow
        g = model.g
        n = model.n
        self.eps_rp = model.eps_rp
        A = model.A

        #Measures
        dIce_gnd    = model.dIce_gnd
        dIce_flt    = model.dIce_flt
        dIce        = model.dIce

        dLat_gnd  = model.dLat_gnd
        dLat_flt  = model.dLat_flt
        dLat_dmn  = model.dLat_dmn

        #Equations

        #Driving Stress
        gradS = grad(surf)
        tau_drv = project(rhoi*g*height*gradS, model.V)
        Ds = dot(tau_drv, model.U)

        #Viscous Dissipation
        epsdot = self.effective_strain_rate(model.U)
        Vd = (2.0*n)/(n+1.0) * A**(-1.0/n) * (epsdot)**((n+1.0)/(2.0*n))

        #Sliding law
        Sl = 0.5 * B2 * dot(model.U,model.U)

        # action :
        Action = (height*Vd + Ds)*dIce + Sl*dIce_gnd #+ Wp*dLat_flt

        # the first variation of the action in the direction of a
        # test function ; the extremum :
        self.mom_F = derivative(Action, model.U, model.Phi)

        # the first variation of the extremum in the direction
        # a trial function ; the Jacobian :
        self.mom_Jac = derivative(self.mom_F, model.U, model.dU)

        self.bc_dmn = [DirichletBC(model.V, (0.0, 0.0), model.ff, model.GAMMA_DMN)]




        solve(self.mom_F == 0, model.U, J = self.mom_Jac, bcs = self.bc_dmn,solver_parameters = model.solve_param)

    def calc_hess(self,param):
        self.mom_H1 = derivative(self.mom_F, param)
        self.mom_Hess = derivative(self.mom_H1, param)


    def epsilon(self, U):
        """
        return the strain-rate tensor of self.U.
        """
        epsdot = sym(grad(U))
        return epsdot

    def effective_strain_rate(self, U):
        """
        return the effective strain rate squared.
        """

        eps = self.epsilon(U)
        exx = eps[0,0]
        eyy = eps[1,1]
        exy = eps[0,1]

        # Second invariant of the strain rate tensor squared
        eps_2 = (exx**2 + eyy**2 + exx*eyy + (exy)**2 + self.eps_rp**2)

        return eps_2
