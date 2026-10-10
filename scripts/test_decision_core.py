"""Synthetic decision-policy tests; these are not trading evidence."""
import copy
import unittest
import importlib.util
from pathlib import Path

class DecisionTests(unittest.TestCase):
    def module(self):
        p=Path(__file__).with_name('decision_core.py')
        self.assertTrue(p.exists(), 'Missing final evidence gate')
        spec=importlib.util.spec_from_file_location('decision_core',p)
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        return m

    def case(self):
        day='2026-10-10'
        checks={k:{'passed':True,'source':'fixture://'+k,'as_of':day} for k in
                ['identity','tradable','liquidity','trend','demand','fundamentals',
                 'market','sector','disclosures','entry']}
        return {'symbol':'TEST','quote_session':day,'reference_session':day,
                'history_session':day,'flow_session':day,'completed_session':True,
                'reference_verified':True,'session_source':'fixture://exchange',
                'checks':checks,'entry':100.,'stop':90.,'target':125.,'cost':1.,
                'cost_basis':'explicit conservative assumption',
                'levels_source':'fixture://confirmed-pivots'}

    def test_complete_case_is_conditional_candidate(self):
        m=self.module();r=m.evaluate(self.case(),as_of='2026-10-10')
        self.assertEqual(r['verdict'],'buy_candidate')
        self.assertAlmostEqual(r['reward_risk'],24/11)
        self.assertFalse(r['order_authorized'])

    def test_absent_checks_never_buy(self):
        m=self.module(); c=self.case();c['checks'].pop('fundamentals')
        r=m.evaluate(c,as_of='2026-10-10')
        self.assertEqual(r['verdict'],'unknown')

    def test_boolean_without_provenance_never_buy(self):
        m=self.module();c=self.case();c['checks']['trend']={'passed':True}
        self.assertEqual(m.evaluate(c,as_of='2026-10-10')['verdict'],'unknown')

    def test_date_mismatch_blocks(self):
        m=self.module()
        for key in ['quote_session','history_session','flow_session']:
            c=self.case();c[key]='2026-10-07'
            self.assertEqual(m.evaluate(c,as_of='2026-10-10')['verdict'],'unknown')

    def test_future_and_old_reference_and_partial_block(self):
        m=self.module()
        for day in ['2026-10-09','2026-10-20']:
            self.assertEqual(m.evaluate(self.case(),as_of=day)['verdict'],'unknown')
        c=self.case();c['completed_session']=False
        self.assertEqual(m.evaluate(c,as_of='2026-10-10')['verdict'],'unknown')

    def test_negative_gate_waits_not_unknown(self):
        m=self.module();c=self.case();c['checks']['entry']['passed']=False
        self.assertEqual(m.evaluate(c,as_of='2026-10-10')['verdict'],'wait')

    def test_rr_floor_and_bad_number_and_missing_cost(self):
        m=self.module();c=self.case();c['target']=115
        self.assertEqual(m.evaluate(c,as_of='2026-10-10')['verdict'],'wait')
        for key in ['entry','stop','target','cost']:
            c=self.case();c[key]=float('nan')
            self.assertEqual(m.evaluate(c,as_of='2026-10-10')['verdict'],'unknown')
        c=self.case();c.pop('cost_basis')
        self.assertEqual(m.evaluate(c,as_of='2026-10-10')['verdict'],'unknown')

    def test_future_dated_check_blocks(self):
        m=self.module();c=self.case();c['checks']['fundamentals']['as_of']='2027-01-01'
        self.assertEqual(m.evaluate(c,as_of='2026-10-10')['verdict'],'unknown')

if __name__=='__main__':unittest.main()
