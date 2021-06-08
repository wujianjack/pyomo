#  ___________________________________________________________________________
#
#  Pyomo: Python Optimization Modeling Objects
#  Copyright 2017 National Technology and Engineering Solutions of Sandia, LLC
#  Under the terms of Contract DE-NA0003525 with National Technology and
#  Engineering Solutions of Sandia, LLC, the U.S. Government retains certain
#  rights in this software.
#  This software is distributed under the 3-clause BSD License.
#  ___________________________________________________________________________

import pyomo.environ as pyo
import pyomo.common.unittest as unittest
from pyomo.common.collections import ComponentSet, ComponentMap
from pyomo.util.subsystems import (
        create_subsystem_block,
        generate_subsystem_blocks,
        TemporarySubsystemManager,
        ParamSweeper,
        )


def _make_simple_model():
    m = pyo.ConcreteModel()

    m.v1 = pyo.Var(bounds=(0, None))
    m.v2 = pyo.Var(bounds=(0, None))
    m.v3 = pyo.Var()
    m.v4 = pyo.Var()

    m.con1 = pyo.Constraint(expr=m.v1*m.v2*m.v3 == m.v4)
    m.con2 = pyo.Constraint(expr=m.v1 + m.v2**2 == 2*m.v4)
    m.con3 = pyo.Constraint(expr=m.v1**2 - m.v3 == 3*m.v4)

    return m


class TestSubsystemBlock(unittest.TestCase):

    def test_square_subsystem(self):
        m = _make_simple_model()

        cons = [m.con2, m.con3]
        vars = [m.v1, m.v2]
        # With m.v3 and m.v4 fixed, m.con2 and m.con3 form a square subsystem
        block = create_subsystem_block(cons, vars)

        self.assertEqual(len(block.vars), 2)
        self.assertEqual(len(block.cons), 2)
        self.assertEqual(len(block.input_vars), 2)
        self.assertEqual(len([v for v in block.component_data_objects(pyo.Var)
            if not v.fixed]), 4)

        block.input_vars.fix()
        self.assertEqual(len([v for v in block.component_data_objects(pyo.Var)
            if not v.fixed]), 2)

        self.assertIs(block.cons[0], m.con2)
        self.assertIs(block.cons[1], m.con3)
        self.assertIs(block.vars[0], m.v1)
        self.assertIs(block.vars[1], m.v2)
        self.assertIs(block.input_vars[0], m.v4)
        self.assertIs(block.input_vars[1], m.v3)

        # Make sure block is not part of the original model's tree. We
        # don't want to alter the user's model at all.
        self.assertIsNot(block.model(), m)

        # Components on the block are references to components on the
        # original model
        for comp in block.component_objects((pyo.Var, pyo.Constraint)):
            self.assertTrue(comp.is_reference())
            for data in comp.values():
                self.assertIs(data.model(), m)

    def test_subsystem_inputs_only(self):
        m = _make_simple_model()

        cons = [m.con2, m.con3]
        block = create_subsystem_block(cons)

        self.assertEqual(len(block.vars), 0)
        self.assertEqual(len(block.input_vars), 4)
        self.assertEqual(len(block.cons), 2)

        self.assertEqual(len([v for v in block.component_data_objects(pyo.Var)
            if not v.fixed]), 4)

        block.input_vars.fix()
        self.assertEqual(len([v for v in block.component_data_objects(pyo.Var)
            if not v.fixed]), 0)

        var_set = ComponentSet([m.v1, m.v2, m.v3, m.v4])
        self.assertIs(block.cons[0], m.con2)
        self.assertIs(block.cons[1], m.con3)
        self.assertIn(block.input_vars[0], var_set)
        self.assertIn(block.input_vars[1], var_set)
        self.assertIn(block.input_vars[2], var_set)
        self.assertIn(block.input_vars[3], var_set)

        # Make sure block is not part of the original model's tree. We
        # don't want to alter the user's model at all.
        self.assertIsNot(block.model(), m)

        # Components on the block are references to components on the
        # original model
        for comp in block.component_objects((pyo.Var, pyo.Constraint)):
            self.assertTrue(comp.is_reference())
            for data in comp.values():
                self.assertIs(data.model(), m)

    @unittest.skipUnless(pyo.SolverFactory("ipopt").available(),
            "Ipopt is not available")
    def test_solve_subsystem(self):
        # This is a test of this function's intended use. We extract a
        # subsystem then solve it without altering the rest of the model.
        m = _make_simple_model()
        ipopt = pyo.SolverFactory("ipopt")

        m.v5 = pyo.Var(initialize=1.0)
        m.c4 = pyo.Constraint(expr=m.v5 == 5.0)

        cons = [m.con2, m.con3]
        vars = [m.v1, m.v2]
        block = create_subsystem_block(cons, vars)

        m.v3.fix(1.0)
        m.v4.fix(2.0)

        # Initialize to avoid converging infeasible due to bad pivots
        m.v1.set_value(1.0)
        m.v2.set_value(1.0)
        ipopt.solve(block)

        # Have solved model to expected values
        self.assertAlmostEqual(m.v1.value, pyo.sqrt(7.0), delta=1e-8)
        self.assertAlmostEqual(m.v2.value, pyo.sqrt(4.0-pyo.sqrt(7.0)),
                delta=1e-8)

        # Rest of model has not changed
        self.assertEqual(m.v5.value, 1.0)

    def test_generate_subsystems_without_fixed_var(self):
        m = _make_simple_model()
        subsystems = [
                ([m.con1], [m.v1, m.v4]),
                ([m.con2, m.con3], [m.v2, m.v3]),
                ]
        other_vars = [
                [m.v2, m.v3],
                [m.v1, m.v4],
                ]
        for i, block in enumerate(generate_subsystem_blocks(subsystems)):
            self.assertIs(block.model(), block)
            var_set = ComponentSet(subsystems[i][1])
            con_set = ComponentSet(subsystems[i][0])
            input_set = ComponentSet(other_vars[i])
            
            self.assertEqual(len(var_set), len(block.vars))
            self.assertEqual(len(con_set), len(block.cons))
            self.assertEqual(len(input_set), len(block.input_vars))
            self.assertTrue(all(var in var_set for var in block.vars[:]))
            self.assertTrue(all(con in con_set for con in block.cons[:]))
            self.assertTrue(
                    all(var in input_set for var in block.input_vars[:]))
            self.assertTrue(all(var.fixed for var in block.input_vars[:]))
            self.assertFalse(any(var.fixed for var in block.vars[:]))

        self.assertFalse(any(var.fixed for var in
            m.component_data_objects(pyo.Var)))

    def test_generate_subsystems_with_fixed_var(self):
        m = _make_simple_model()
        m.v4.fix()
        subsystems = [
                ([m.con1], [m.v1]),
                ([m.con2, m.con3], [m.v2, m.v3]),
                ]
        other_vars = [
                [m.v2, m.v3],
                [m.v1],
                ]
        for i, block in enumerate(generate_subsystem_blocks(subsystems)):
            self.assertIs(block.model(), block)
            var_set = ComponentSet(subsystems[i][1])
            con_set = ComponentSet(subsystems[i][0])
            input_set = ComponentSet(other_vars[i])
            
            self.assertEqual(len(var_set), len(block.vars))
            self.assertEqual(len(con_set), len(block.cons))
            self.assertEqual(len(input_set), len(block.input_vars))
            self.assertTrue(all(var in var_set for var in block.vars[:]))
            self.assertTrue(all(con in con_set for con in block.cons[:]))
            self.assertTrue(
                    all(var in input_set for var in block.input_vars[:]))
            self.assertTrue(all(var.fixed for var in block.input_vars[:]))
            self.assertFalse(any(var.fixed for var in block.vars[:]))

        self.assertFalse(m.v1.fixed)
        self.assertFalse(m.v2.fixed)
        self.assertFalse(m.v3.fixed)
        self.assertTrue(m.v4.fixed)

    def test_generate_subsystems_include_fixed_var(self):
        m = _make_simple_model()
        m.v4.fix()
        subsystems = [
                ([m.con1], [m.v1]),
                ([m.con2, m.con3], [m.v2, m.v3]),
                ]
        other_vars = [
                [m.v2, m.v3, m.v4],
                [m.v1, m.v4],
                ]
        for i, block in enumerate(generate_subsystem_blocks(
            subsystems,
            include_fixed=True,
            )):
            self.assertIs(block.model(), block)
            var_set = ComponentSet(subsystems[i][1])
            con_set = ComponentSet(subsystems[i][0])
            input_set = ComponentSet(other_vars[i])
            
            self.assertEqual(len(var_set), len(block.vars))
            self.assertEqual(len(con_set), len(block.cons))
            self.assertEqual(len(input_set), len(block.input_vars))
            self.assertTrue(all(var in var_set for var in block.vars[:]))
            self.assertTrue(all(con in con_set for con in block.cons[:]))
            self.assertTrue(
                    all(var in input_set for var in block.input_vars[:]))
            self.assertTrue(all(var.fixed for var in block.input_vars[:]))
            self.assertFalse(any(var.fixed for var in block.vars[:]))

        self.assertFalse(m.v1.fixed)
        self.assertFalse(m.v2.fixed)
        self.assertFalse(m.v3.fixed)
        self.assertTrue(m.v4.fixed)

    def test_generate_subsystems_dont_fix_inputs(self):
        m = _make_simple_model()
        subsystems = [
                ([m.con1], [m.v1]),
                ([m.con2, m.con3], [m.v2, m.v3]),
                ]
        other_vars = [
                [m.v2, m.v3, m.v4],
                [m.v1, m.v4],
                ]
        for i, block in enumerate(generate_subsystem_blocks(
            subsystems,
            fix_inputs=False,
            )):
            self.assertIs(block.model(), block)
            var_set = ComponentSet(subsystems[i][1])
            con_set = ComponentSet(subsystems[i][0])
            input_set = ComponentSet(other_vars[i])
            
            self.assertEqual(len(var_set), len(block.vars))
            self.assertEqual(len(con_set), len(block.cons))
            self.assertEqual(len(input_set), len(block.input_vars))
            self.assertTrue(all(var in var_set for var in block.vars[:]))
            self.assertTrue(all(con in con_set for con in block.cons[:]))
            self.assertTrue(
                    all(var in input_set for var in block.input_vars[:]))
            self.assertFalse(any(var.fixed for var in block.input_vars[:]))
            self.assertFalse(any(var.fixed for var in block.vars[:]))

        self.assertFalse(m.v1.fixed)
        self.assertFalse(m.v2.fixed)
        self.assertFalse(m.v3.fixed)
        self.assertFalse(m.v4.fixed)

    def test_generate_dont_fix_inputs_with_fixed_var(self):
        m = _make_simple_model()
        m.v4.fix()
        subsystems = [
                ([m.con1], [m.v1]),
                ([m.con2, m.con3], [m.v2, m.v3]),
                ]
        other_vars = [
                [m.v2, m.v3],
                [m.v1],
                ]
        for i, block in enumerate(generate_subsystem_blocks(
            subsystems,
            fix_inputs=False,
            )):
            self.assertIs(block.model(), block)
            var_set = ComponentSet(subsystems[i][1])
            con_set = ComponentSet(subsystems[i][0])
            input_set = ComponentSet(other_vars[i])
            
            self.assertEqual(len(var_set), len(block.vars))
            self.assertEqual(len(con_set), len(block.cons))
            self.assertEqual(len(input_set), len(block.input_vars))
            self.assertTrue(all(var in var_set for var in block.vars[:]))
            self.assertTrue(all(con in con_set for con in block.cons[:]))
            self.assertTrue(
                    all(var in input_set for var in block.input_vars[:]))
            self.assertFalse(m.v1.fixed)
            self.assertFalse(m.v2.fixed)
            self.assertFalse(m.v3.fixed)
            self.assertTrue(m.v4.fixed)

        self.assertFalse(m.v1.fixed)
        self.assertFalse(m.v2.fixed)
        self.assertFalse(m.v3.fixed)
        self.assertTrue(m.v4.fixed)


class TestTemporarySubsystemManager(unittest.TestCase):

    def test_context(self):
        m = _make_simple_model()

        to_fix = [m.v4]
        to_deactivate = [m.con1]
        to_reset = [m.v1]

        m.v1.set_value(1.5)

        with TemporarySubsystemManager(to_fix, to_deactivate, to_reset):
            self.assertEqual(m.v1.value, 1.5)
            self.assertTrue(m.v4.fixed)
            self.assertFalse(m.con1.active)

            m.v1.set_value(2.0)
            m.v4.set_value(3.0)

        self.assertEqual(m.v1.value, 1.5)
        self.assertEqual(m.v4.value, 3.0)
        self.assertFalse(m.v4.fixed)
        self.assertTrue(m.con1.active)

    def test_context_some_redundant(self):
        m = _make_simple_model()

        to_fix = [m.v2, m.v4]
        to_deactivate = [m.con1, m.con2]
        to_reset = [m.v1]

        m.v1.set_value(1.5)
        m.v2.fix()
        m.con1.deactivate()

        with TemporarySubsystemManager(to_fix, to_deactivate, to_reset):
            self.assertEqual(m.v1.value, 1.5)
            self.assertTrue(m.v2.fixed)
            self.assertTrue(m.v4.fixed)
            self.assertFalse(m.con1.active)
            self.assertFalse(m.con2.active)

            m.v1.set_value(2.0)
            m.v2.set_value(3.0)

        self.assertEqual(m.v1.value, 1.5)
        self.assertEqual(m.v2.value, 3.0)
        self.assertTrue(m.v2.fixed)
        self.assertFalse(m.v4.fixed)
        self.assertTrue(m.con2.active)
        self.assertFalse(m.con1.active)

    @unittest.skipUnless(pyo.SolverFactory("ipopt").available(),
            "Ipopt is not available")
    def test_fix_then_solve(self):
        # This is a test of the expected use case. We have a (square)
        # subsystem that we can solve easily after fixing and deactivating
        # certain variables and constraints.

        m = _make_simple_model()
        ipopt = pyo.SolverFactory("ipopt")

        # Initialize to avoid converging infeasible due to bad pivots
        m.v1.set_value(1.0)
        m.v2.set_value(1.0)
        m.v3.set_value(1.0)
        m.v4.set_value(2.0)

        with TemporarySubsystemManager(to_fix=[m.v3, m.v4],
                to_deactivate=[m.con1]):
            # Solve the subsystem with m.v1, m.v2 unfixed and
            # m.con2, m.con3 inactive.
            ipopt.solve(m)

        # Have solved model to expected values
        self.assertAlmostEqual(m.v1.value, pyo.sqrt(7.0), delta=1e-8)
        self.assertAlmostEqual(m.v2.value, pyo.sqrt(4.0-pyo.sqrt(7.0)),
                delta=1e-8)


class TestParamSweeper(unittest.TestCase):

    def test_set_values(self):
        m = _make_simple_model()

        n_scenario = 2
        input_values = ComponentMap([
            (m.v3, [1.3, 2.3]),
            (m.v4, [1.4, 2.4]),
            ])

        to_fix = [m.v3, m.v4]
        to_deactivate = [m.con1]

        with ParamSweeper(2, input_values, to_fix=to_fix,
                to_deactivate=to_deactivate) as sweeper:
            self.assertFalse(m.v1.fixed)
            self.assertFalse(m.v2.fixed)
            self.assertTrue(m.v3.fixed)
            self.assertTrue(m.v4.fixed)
            self.assertFalse(m.con1.active)
            self.assertTrue(m.con2.active)
            self.assertTrue(m.con3.active)
            for i, (inputs, outputs) in enumerate(sweeper):
                for var, val in inputs.items():
                    self.assertEqual(var.value, val)
                    self.assertEqual(var.value, input_values[var][i])

        # Values have been reset after exit.
        self.assertIs(m.v3.value, None)
        self.assertIs(m.v4.value, None)


    def test_output_values(self):
        m = _make_simple_model()

        n_scenario = 2
        input_values = ComponentMap([
            (m.v3, [1.3, 2.3]),
            (m.v4, [1.4, 2.4]),
            ])

        output_values = ComponentMap([
            (m.v1, [1.1, 2.1]),
            (m.v2, [1.2, 2.2]),
            ])

        to_fix = [m.v3, m.v4]
        to_deactivate = [m.con1]

        with ParamSweeper(2, input_values, to_fix=to_fix,
                to_deactivate=to_deactivate) as sweeper:
            self.assertFalse(m.v1.fixed)
            self.assertFalse(m.v2.fixed)
            self.assertTrue(m.v3.fixed)
            self.assertTrue(m.v4.fixed)
            self.assertFalse(m.con1.active)
            self.assertTrue(m.con2.active)
            self.assertTrue(m.con3.active)
            for i, (inputs, outputs) in enumerate(sweeper):
                for var, val in inputs.items():
                    self.assertEqual(var.value, val)
                    self.assertEqual(var.value, input_values[var][i])

                for var, val in outputs.items():
                    self.assertEqual(var.value, output_values[var][i])

        # Values have been reset after exit.
        self.assertIs(m.v3.value, None)
        self.assertIs(m.v4.value, None)


    @unittest.skipUnless(pyo.SolverFactory("ipopt").available(),
            "Ipopt is not available")
    def test_with_solve(self):
        m = _make_simple_model()
        ipopt = pyo.SolverFactory("ipopt")

        n_scenario = 2
        input_values = ComponentMap([
            (m.v3, [1.3, 2.3]),
            (m.v4, [1.4, 2.4]),
            ])

        _v1_val_1 = pyo.sqrt(3*1.4+1.3)
        _v1_val_2 = pyo.sqrt(3*2.4+2.3)
        _v2_val_1 = pyo.sqrt(2*1.4 - _v1_val_1)
        _v2_val_2 = pyo.sqrt(2*2.4 - _v1_val_2)
        output_values = ComponentMap([
            (m.v1, [_v1_val_1, _v1_val_2]),
            (m.v2, [_v2_val_1, _v2_val_2]),
            ])

        to_fix = [m.v3, m.v4]
        to_deactivate = [m.con1]
        to_reset = [m.v1, m.v2]

        # Initialize values so we don't fail due to bad initialization
        m.v1.set_value(1.0)
        m.v2.set_value(1.0)

        with ParamSweeper(n_scenario, input_values, output_values,
                to_fix=to_fix,
                to_deactivate=to_deactivate,
                to_reset=to_reset,
                ) as sweeper:
            self.assertFalse(m.v1.fixed)
            self.assertFalse(m.v2.fixed)
            self.assertTrue(m.v3.fixed)
            self.assertTrue(m.v4.fixed)
            self.assertFalse(m.con1.active)
            self.assertTrue(m.con2.active)
            self.assertTrue(m.con3.active)
            for i, (inputs, outputs) in enumerate(sweeper):
                ipopt.solve(m)

                for var, val in inputs.items():
                    # These values should not have been altered.
                    # I believe exact equality should be appropriate here.
                    self.assertEqual(var.value, val)
                    self.assertEqual(var.value, input_values[var][i])

                for var, val in outputs.items():
                    self.assertAlmostEqual(var.value, val, delta=1e-8)
                    self.assertAlmostEqual(var.value, output_values[var][i],
                            delta=1e-8)

        # Values have been reset after exit.
        self.assertIs(m.v1.value, 1.0)
        self.assertIs(m.v2.value, 1.0)
        self.assertIs(m.v3.value, None)
        self.assertIs(m.v4.value, None)


if __name__ == '__main__':
    unittest.main()
