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

import pyomo.environ as pe
import pyomo.common.unittest as unittest
import pyomo.contrib.alternative_solutions.aos_utils as au

class TestAOSUtilsUnit(unittest.TestCase):
    def get_two_objective_model(self):
        m = pe.ConcreteModel()
        m.b1 = pe.Block()
        m.b2 = pe.Block()
        m.x = pe.Var()
        m.y = pe.Var()
        m.b1.o = pe.Objective(expr=m.x)
        m.b2.o = pe.Objective([0,1])
        m.b2.o[0] = pe.Objective(expr=m.y)
        m.b2.o[1] = pe.Objective(expr=m.x+m.y)
        return m
        
    def test_multiple_objectives(self):
        m = self.get_two_objective_model()
        assert_text = ("Model has 3 active objective functions, exactly one "
                       "is required.")
        with self.assertRaisesRegex(AssertionError, assert_text):
            au._get_active_objective(m)
            
    def test_no_objectives(self):
        m = self.get_two_objective_model()
        m.b1.o.deactivate()
        m.b2.o.deactivate()
        assert_text = ("Model has 0 active objective functions, exactly one "
                       "is required.")
        with self.assertRaisesRegex(AssertionError, assert_text):
            au._get_active_objective(m)

    def test_one_objective(self):
        m = self.get_two_objective_model()
        m.b1.o.deactivate()
        m.b2.o[0].deactivate()
        self.assertEqual(m.b2.o[1], au._get_active_objective(m))
    
    def test_aos_block(self):
        m = self.get_two_objective_model()
        block_name = 'test_block'
        b = au._add_aos_block(m, block_name)
        self.assertEqual(b.name, block_name)
        self.assertEqual(b.ctype, pe.Block)
    
    def get_simple_model(self, sense = pe.minimize):
        m = pe.ConcreteModel()
        m.x = pe.Var()
        m.y = pe.Var()
        m.o = pe.Objective(expr=m.x+m.y, sense=sense)
        return m
    
    def test_no_obj_constraint(self):
        m = self.get_simple_model()
        cons = au._add_objective_constraint(m, m.o, 2, None, None)
        self.assertEqual(cons, [])
        self.assertEqual(m.find_component('optimality_tol_rel'), None)
        self.assertEqual(m.find_component('optimality_tol_abs'), None)
        
    def test_min_rel_obj_constraint(self):
        m = self.get_simple_model()
        cons = au._add_objective_constraint(m, m.o, 2, 0.1, None)
        self.assertEqual(len(cons), 1)
        self.assertEqual(m.find_component('optimality_tol_rel'), cons[0])
        self.assertEqual(m.find_component('optimality_tol_abs'), None)
        self.assertEqual(2.2, cons[0].upper)
        self.assertEqual(None, cons[0].lower)

    def test_min_abs_obj_constraint(self):
        m = self.get_simple_model()
        cons = au._add_objective_constraint(m, m.o, 2, None, 1)
        self.assertEqual(len(cons), 1)
        self.assertEqual(m.find_component('optimality_tol_rel'), None)
        self.assertEqual(m.find_component('optimality_tol_abs'), cons[0])
        self.assertEqual(3, cons[0].upper)
        self.assertEqual(None, cons[0].lower)

    def test_min_both_obj_constraint(self):
        m = self.get_simple_model()
        cons = au._add_objective_constraint(m, m.o, -10, 0.3, 5)
        m.pprint()
        self.assertEqual(len(cons), 2)
        self.assertEqual(m.find_component('optimality_tol_rel'), cons[0])
        self.assertEqual(m.find_component('optimality_tol_abs'), cons[1])
        self.assertEqual(-7, cons[0].upper)
        self.assertEqual(None, cons[0].lower)
        self.assertEqual(-5, cons[1].upper)
        self.assertEqual(None, cons[1].lower)
        
    def test_max_both_obj_constraint(self):
        m = self.get_simple_model(sense=pe.maximize)
        cons = au._add_objective_constraint(m, m.o, -1, 0.3, 1)
        self.assertEqual(len(cons), 2)
        self.assertEqual(m.find_component('optimality_tol_rel'), cons[0])
        self.assertEqual(m.find_component('optimality_tol_abs'), cons[1])
        self.assertEqual(None, cons[0].upper)
        self.assertEqual(-1.3, cons[0].lower)
        self.assertEqual(None, cons[1].upper)
        self.assertEqual(-2, cons[1].lower)

    def test_max_both_obj_constraint2(self):
        m = self.get_simple_model(sense=pe.maximize)
        cons = au._add_objective_constraint(m, m.o, 20, 0.5, 11)
        self.assertEqual(len(cons), 2)
        self.assertEqual(m.find_component('optimality_tol_rel'), cons[0])
        self.assertEqual(m.find_component('optimality_tol_abs'), cons[1])
        self.assertEqual(None, cons[0].upper)
        self.assertEqual(10, cons[0].lower)
        self.assertEqual(None, cons[1].upper)
        self.assertEqual(9, cons[1].lower)

    def get_var_model(self):
        m = pe.ConcreteModel()
        m.b1 = pe.Block()
        m.b2 = pe.Block()
        m.b1.sb = pe.Block()
        m.b2.sb = pe.Block()
        m.c = pe.Var(domain=pe.Reals)
        m.b = pe.Var(domain=pe.Binary)
        m.i = pe.var(domain=pe.Integers)
        m.c_f = pe.Var(domain=pe.Reals)
        m.b_f = pe.Var(domain=pe.Binary)
        m.i_f = pe.var(domain=pe.Integers)
        m.c_f.fix(0)
        m.b_f.fix(0)
        m.i_f.fix(0)
        m.b1.o = pe.Objective(expr=m.x)
        m.b2.o = pe.Objective([0,1])
        m.b2.o[0] = pe.Objective(expr=m.y)
        m.b2.o[1] = pe.Objective(expr=m.x+m.y)
        return m

if __name__ == '__main__':
    unittest.main()