import sys
sys.path.insert(0,'../code/')
import os
import argparse
from fenics import *
import model
import solver
import matplotlib.pyplot as plt
import numpy as np
import fenics_util as fu
import time
import datetime
import pickle
from IPython import embed


def main(maxiter, rc_inv, pflag, outdir, dd):

    #Load Data
    data_mesh = Mesh(''.join([dd,'smith450m_mesh.xml']))
    Q = FunctionSpace(data_mesh, 'DG', 0)
    bed = Function(Q,''.join([dd,'smith450m_mesh_bed.xml']), name = "bed")
    thick = Function(Q,''.join([dd,'smith450m_mesh_thick.xml']), name = "thick")
    mask = Function(Q,''.join([dd,'smith450m_mesh_mask.xml']), name = "mask")
    u_obs = Function(Q,''.join([dd,'smith450m_mesh_u_obs.xml']), name = "u_obs")
    v_obs = Function(Q,''.join([dd,'smith450m_mesh_v_obs.xml']), name = "v_obs")
    u_std = Function(Q,''.join([dd,'smith450m_mesh_u_std.xml']), name = "u_std")
    v_std = Function(Q,''.join([dd,'smith450m_mesh_v_std.xml']), name = "v_std")
    mask_vel = Function(Q,''.join([dd,'smith450m_mesh_mask_vel.xml']), name = "mask_vel")
    B_mod = Function(Q,''.join([dd,'smith450m_mesh_mask_B_mod.xml']), name = "B_mod")


    #Generate model mesh
    gf = 'grid_data.npz'
    npzfile = np.load(''.join([dd,'grid_data.npz']))
    nx = int(npzfile['nx'])
    ny = int(npzfile['ny'])
    xlim = npzfile['xlim']
    ylim = npzfile['ylim']

    mesh = RectangleMesh(Point(xlim[0],ylim[0]), Point(xlim[-1], ylim[-1]), nx, ny)

    #Initialize Model
    param = {
            'outdir' : outdir,
            'rc_inv': rc_inv, #alpha + beta
            'inv_options': {'maxiter': maxiter}
            }

    mdl = model.model(mesh,mask, param)
    mdl.init_bed(bed)
    mdl.init_thick(thick)
    mdl.gen_surf()
    mdl.init_mask(mask)
    mdl.init_vel_obs(u_obs,v_obs,mask_vel,u_std,v_std)
    mdl.init_lat_dirichletbc()
    mdl.init_bmelt(Constant(0.0))
    mdl.gen_alpha()
    #mdl.init_alpha(Constant(sqrt(6000))) #Initialize using uniform alpha
    mdl.init_beta(sqrt(B_mod))            #Comment to use uniform Bglen
    mdl.label_domain()

    #Inversion
    slvr = solver.ssa_solver(mdl)

    if pflag == 0:
        slvr.inversion(slvr.alpha)
    elif pflag == 1:
        slvr.inversion(slvr.beta)
    elif pflag == 2:
        slvr.inversion([slvr.alpha,slvr.beta])

    #Plots for quick output evaluation
    B2 = project(slvr.alpha*slvr.alpha,mdl.Q)
    F_vals = [x for x in slvr.F_vals if x > 0]

    fu.plot_variable(B2, 'B2', mdl.param['outdir'])
    fu.plot_inv_conv(F_vals, 'convergence', mdl.param['outdir'])


    #Output model variables in ParaView+Fenics friendly format
    outdir = mdl.param['outdir']
    pickle.dump( mdl.param, open( ''.join([outdir,'param.p']), "wb" ) )

    File(''.join([outdir,'mesh.xml'])) << mdl.mesh
    File(''.join([outdir,'data_mesh.xml'])) << data_mesh

    vtkfile = File(''.join([outdir,'U.pvd']))
    xmlfile = File(''.join([outdir,'U.xml']))
    vtkfile << slvr.U
    xmlfile << slvr.U

    vtkfile = File(''.join([outdir,'beta.pvd']))
    xmlfile = File(''.join([outdir,'beta.xml']))
    vtkfile << slvr.beta
    xmlfile << slvr.beta

    vtkfile = File(''.join([outdir,'bed.pvd']))
    xmlfile = File(''.join([outdir,'bed.xml']))
    vtkfile << mdl.bed
    xmlfile << mdl.bed

    vtkfile = File(''.join([outdir,'thick.pvd']))
    xmlfile = File(''.join([outdir,'thick.xml']))
    H = project(mdl.H, mdl.M)
    vtkfile << H
    xmlfile << H

    vtkfile = File(''.join([outdir,'mask.pvd']))
    xmlfile = File(''.join([outdir,'mask.xml']))
    vtkfile << mdl.mask
    xmlfile << mdl.mask

    vtkfile = File(''.join([outdir,'data_mask.pvd']))
    xmlfile = File(''.join([outdir,'data_mask.xml']))
    vtkfile << mask
    xmlfile << mask

    vtkfile = File(''.join([outdir,'mask_vel.pvd']))
    xmlfile = File(''.join([outdir,'mask_vel.xml']))
    vtkfile << mdl.mask_vel
    xmlfile << mdl.mask_vel

    vtkfile = File(''.join([outdir,'u_obs.pvd']))
    xmlfile = File(''.join([outdir,'u_obs.xml']))
    vtkfile << mdl.u_obs
    xmlfile << mdl.u_obs

    vtkfile = File(''.join([outdir,'v_obs.pvd']))
    xmlfile = File(''.join([outdir,'v_obs.xml']))
    vtkfile << mdl.v_obs
    xmlfile << mdl.v_obs

    vtkfile = File(''.join([outdir,'u_std.pvd']))
    xmlfile = File(''.join([outdir,'u_std.xml']))
    vtkfile << mdl.u_std
    xmlfile << mdl.u_std

    vtkfile = File(''.join([outdir,'v_std.pvd']))
    xmlfile = File(''.join([outdir,'v_std.xml']))
    vtkfile << mdl.v_std
    xmlfile << mdl.v_std

    vtkfile = File(''.join([outdir,'uv_obs.pvd']))
    xmlfile = File(''.join([outdir,'uv_obs.xml']))
    U_obs = project((mdl.v_obs**2 + mdl.u_obs**2)**(1.0/2.0), mdl.M)
    vtkfile << U_obs
    xmlfile << U_obs

    vtkfile = File(''.join([outdir,'alpha.pvd']))
    xmlfile = File(''.join([outdir,'alpha.xml']))
    vtkfile << mdl.alpha
    xmlfile << mdl.alpha

    vtkfile = File(''.join([outdir,'Bglen.pvd']))
    xmlfile = File(''.join([outdir,'Bglen.xml']))
    Bglen = project(mdl.beta*mdl.beta,mdl.M)
    vtkfile << Bglen
    xmlfile << Bglen

    vtkfile = File(''.join([outdir,'B2.pvd']))
    xmlfile = File(''.join([outdir,'B2.xml']))
    vtkfile << B2
    xmlfile << B2

    vtkfile = File(''.join([outdir,'surf.pvd']))
    xmlfile = File(''.join([outdir,'surf.xml']))
    vtkfile << mdl.surf
    xmlfile << mdl.surf

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--maxiter', dest='maxiter', type=int, help='Maximum number of inversion iterations')
    parser.add_argument('-r', '--rc_inv', dest='rc_inv', nargs=5, type=float, required=True, help='Scaling Constants')
    parser.add_argument('-p', '--parameters', dest='pflag', choices=[0, 1, 2], type=int, required=True, help='Inversion parameters: alpha (0), beta (1), alpha and beta (2)')

    parser.add_argument('-o', '--outdir', dest='outdir', type=str, help='Directory to store output')
    parser.add_argument('-d', '--datadir', dest='dd', type=str, required=True, help='Directory with input data')

    parser.set_defaults(maxiter=15)
    args = parser.parse_args()

    maxiter = args.maxiter
    rc_inv = args.rc_inv
    pflag = args.pflag
    outdir = args.outdir
    dd = args.dd

    if not outdir:
        outdir = ''.join(['./run_inv_', datetime.datetime.now().strftime("%m%d%H%M%S"), '/'])
        if not os.path.isdir(outdir):
            print('Creating output directory: {0}'.format(outdir))
            os.makedirs(outdir)
        else:
            sys.exit(2)

    main(maxiter, rc_inv, pflag, outdir, dd)
