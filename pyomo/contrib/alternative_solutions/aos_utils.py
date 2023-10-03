#  ___________________________________________________________________________
#
#  Pyomo: Python Optimization Modeling Objects
#  Copyright (c) 2008-2022
#  National Technology and Engineering Solutions of Sandia, LLC
#  Under the terms of Contract DE-NA0003525 with National Technology and
#  Engineering Solutions of Sandia, LLC, the U.S. Government retains certain
#  rights in this software.
#  This software is distributed under the 3-clause BSD License.
#  ___________________________________________________________________________

import sys

from numpy.random import normal
from numpy.linalg import norm

import pyomo.environ as pe
from pyomo.common.modeling import unique_component_name
from pyomo.common.collections import ComponentSet
import pyomo.util.vars_from_expressions as vfe

def _get_active_objective(model):
    '''
    Finds and returns the active objective function for a model. Currently 
    assume that there is exactly one active objective.
    '''
    
    active_objs = []
    for o in model.component_data_objects(pe.Objective, active=True):
        objs = o.values() if o.is_indexed() else (o,)
        for obj in objs:
            active_objs.append(obj)
    assert len(active_objs) == 1, \
        "Model has {} active objective functions, exactly one is required.".\
            format(len(active_objs))
    
    return active_objs[0]

def _add_aos_block(model, name='_aos_block'):
    '''Adds an alternative optimal solution block with a unique name.'''
    aos_block = pe.Block()
    model.add_component(unique_component_name(model, name), aos_block)
    return aos_block

def _add_objective_constraint(aos_block, objective, objective_value, 
                             rel_opt_gap, abs_opt_gap):
    '''
    Adds a relative and/or absolute objective function constraint to the 
    specified block.
    '''
    
    assert rel_opt_gap is None or rel_opt_gap >= 0.0, \
        'rel_opt_gap must be None of >= 0.0'
    assert abs_opt_gap is None or abs_opt_gap >= 0.0, \
        'abs_opt_gap must be None of >= 0.0'
    
    objective_constraints = []
    
    objective_is_min = objective.is_minimizing()
    objective_expr = objective.expr

    objective_sense = -1
    if objective_is_min:
        objective_sense = 1
        
    if rel_opt_gap is not None:
        objective_cutoff = objective_value + objective_sense * rel_opt_gap *\
            abs(objective_value)

        if objective_is_min:
            aos_block.optimality_tol_rel = \
                pe.Constraint(expr=objective_expr <= \
                              objective_cutoff)
        else:
            aos_block.optimality_tol_rel = \
                pe.Constraint(expr=objective_expr >= \
                              objective_cutoff)
        objective_constraints.append(aos_block.optimality_tol_rel)
    
    if abs_opt_gap is not None:
        objective_cutoff = objective_value + objective_sense \
            * abs_opt_gap

        if objective_is_min:
            aos_block.optimality_tol_abs = \
                pe.Constraint(expr=objective_expr <= \
                              objective_cutoff)
        else:
            aos_block.optimality_tol_abs = \
                pe.Constraint(expr=objective_expr >= \
                              objective_cutoff)
        objective_constraints.append(aos_block.optimality_tol_abs)
        
    return objective_constraints

def _get_random_direction(num_dimensions):
    '''
    Get a unit vector of dimension num_dimensions by sampling from and 
    normalizing a standard multivariate Gaussian distribution.
    '''
    idx = 0
    while idx < 100:
        samples = normal(size=num_dimensions)
        samples_norm = norm(samples)
        if samples_norm > 1e-4:
            return samples / samples_norm
        idx += 1
    raise Exception

def _filter_model_variables(variable_set, var_generator, 
                            include_continuous=True, include_binary=True, 
                            include_integer=True, include_fixed=False):
    '''Filters variables from a variable generator and adds them to a set.'''
    for var in var_generator:
        if var in variable_set or var.is_fixed() and not include_fixed:
            continue
        if (var.is_continuous() and include_continuous or
                var.is_binary() and include_binary or
                var.is_integer() and include_integer):
            variable_set.add(var)

def get_model_variables(model, components='all', include_continuous=True, 
                        include_binary=True, include_integer=True, 
                        include_fixed=False):
    '''
    Gathers and returns all variables or a subset of variables from a Pyomo 
    model.

        Parameters
        ----------
        model : ConcreteModel
            A concrete Pyomo model.
        components: 'all' or a collection Pyomo components
            The components from which variables should be collected. 'all' 
            indicates that all variables will be included. Alternatively, a 
            collection of Pyomo Blocks, Constraints, or Variables (indexed or
            non-indexed) from which variables will be gathered can be provided. 
            By default all variables in sub-Blocks will be added if a Block 
            element is provided. A tuple element with the format (Block, False) 
            indicates that only variables from the Block should be added but 
            not any of its sub-Blocks.
        include_continuous : boolean
            Boolean indicating that continuous variables should be included.
        include_binary : boolean
            Boolean indicating that binary variables should be included.
        include_integer : boolean
            Boolean indicating that integer variables should be included.
        include_fixed : boolean
            Boolean indicating that fixed variables should be included.
             
        Returns
        -------
        variable_set
            A Pyomo ComponentSet containing _GeneralVarData variables.
    '''
    
    variable_set = ComponentSet()
    if components == 'all':
        var_generator = vfe.get_vars_from_components(model, pe.Constraint, 
                                                     include_fixed=\
                                                         include_fixed)
        _filter_model_variables(variable_set, var_generator, 
                                include_continuous, include_binary, 
                                include_integer, include_fixed)
    else:             
        for comp in components:
            if (hasattr(comp, 'ctype') and comp.ctype == pe.Block):
                blocks = comp.values() if comp.is_indexed() else (comp,)
                for item in blocks:
                    variables = vfe.get_vars_from_components(item, 
                         pe.Constraint, include_fixed=include_fixed)
                    _filter_model_variables(variable_set, variables, 
                        include_continuous, include_binary, include_integer, 
                        include_fixed)
            elif (isinstance(comp, tuple) and isinstance(comp[1], bool) and 
                  hasattr(comp[0], 'ctype') and comp[0].ctype == pe.Block):
                block = comp[0]
                descend_into = pe.Block if comp[1] else False
                blocks = block.values() if block.is_indexed() else (block,)
                for item in blocks:
                    variables = vfe.get_vars_from_components(item, 
                         pe.Constraint, include_fixed=include_fixed, 
                         descend_into=descend_into)
                    _filter_model_variables(variable_set, variables, 
                        include_continuous, include_binary, include_integer, 
                        include_fixed)   
            elif hasattr(comp, 'ctype') and comp.ctype == pe.Constraint:
                constraints = comp.values() if comp.is_indexed() else (comp,)
                for item in constraints:
                    variables = pe.expr.identify_variables(item.expr,
                                               include_fixed=include_fixed)
                    _filter_model_variables(variable_set, variables, 
                        include_continuous, include_binary, include_integer, 
                        include_fixed)   
            elif (hasattr(comp, 'ctype') and comp.ctype == pe.Var):
                variables = comp.values() if comp.is_indexed() else (comp,)
                _filter_model_variables(variable_set, variables, 
                    include_continuous, include_binary, include_integer, 
                    include_fixed)
            else:
                print(('No variables added for unrecognized component {}.').
                      format(comp))
                
    return variable_set