import copy, unittest
from trust_lab import evaluate, check_sample, LabError

class TrustTests(unittest.TestCase):
    def setUp(self):
        self.state={f'V{i}':{'trust':1 if i==5 else 5,'revoked':False,'blocked_until':0} for i in range(1,6)}
        self.good=dict(t0=0,t1=10,x0=0,x1=100,speed_kmh=36)
        self.bad=dict(self.good,speed_kmh=250)
        self.votes=[{'vehicle':f'V{i}','suspicious':True} for i in range(1,5)]
    def test_normal_even_with_false_accusations(self):
        out=evaluate(self.state,'V5',self.votes,self.good,100)
        self.assertFalse(out['accepted']); self.assertEqual(out['state'],self.state)
    def test_speed_and_rewards(self):
        out=evaluate(self.state,'V5',self.votes,self.bad,100)
        self.assertEqual(out['rewards'],{'V1':7,'V2':5,'V3':5,'V4':5})
        self.assertEqual(out['state']['V5']['trust'],0)
        self.assertEqual(out['state']['V5']['blocked_until'],160)
    def test_position(self):
        self.assertEqual(check_sample(dict(self.good,x1=5000)),['impossible_displacement'])
    def test_minimum_four(self):
        self.assertFalse(evaluate(self.state,'V5',self.votes[:3],self.bad,100)['accepted'])
    def test_tie_no_penalty(self):
        self.votes[2]['suspicious']=False; self.votes[3]['suspicious']=False
        self.assertFalse(evaluate(self.state,'V5',self.votes,self.bad,100)['accepted'])
    def test_duplicate_rejected(self):
        with self.assertRaises(LabError): evaluate(self.state,'V5',self.votes+[self.votes[0]],self.bad,100)
    def test_soft_block(self):
        self.state['V1']['blocked_until']=160
        with self.assertRaises(LabError): evaluate(self.state,'V5',self.votes,self.bad,100)
        self.assertTrue(evaluate(self.state,'V5',self.votes,self.bad,160)['accepted'])
    def test_revocation(self):
        out=evaluate(self.state,'V5',self.votes,self.bad,100)
        out=evaluate(out['state'],'V5',self.votes,self.bad,101)
        self.assertEqual(out['state']['V5']['trust'],-1); self.assertTrue(out['state']['V5']['revoked'])
        with self.assertRaises(LabError): evaluate(out['state'],'V5',self.votes,self.bad,102)
    def test_invalid_sample(self):
        for sample in (dict(self.good,t1=0),dict(self.good,speed_kmh=float('nan')),dict(self.good,x1='x')):
            with self.assertRaises(LabError): check_sample(sample)
    def test_unknown_and_self(self):
        for vehicle in ('stranger','V5'):
            with self.assertRaises(LabError): evaluate(self.state,'V5',[{'vehicle':vehicle,'suspicious':True}],self.bad,100)

if __name__=='__main__': unittest.main(verbosity=2)
