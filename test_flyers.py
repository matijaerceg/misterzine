import unittest
from tools.flyer_catalog import apply_flyers


class FlyerTests(unittest.TestCase):
    def test_exact_precedes_declared_family_and_title_never_matches(self):
        rows = [dict(base='Arcade', sn='clone', family='parent'),
                dict(base='Arcade', sn='other', family='parent'),
                dict(base='Arcade', title='parent', sn='missing'),
                dict(base='Console', sn='parent')]
        result = apply_flyers(rows, {'assets': {'clone': {}, 'parent': {}}})
        self.assertEqual(result, dict(exact=1, family=1, missing=1))
        self.assertEqual(rows[0]['media_key'], 'clone')
        self.assertEqual(rows[1]['media_key'], 'parent')
        self.assertEqual(rows[0]['media_slots'], ['flyer'])
        self.assertNotIn('media_key', rows[2])
        self.assertNotIn('media_key', rows[3])

    def test_rerun_drops_unhosted_media_and_is_stable(self):
        rows = [dict(base='Arcade', sn='a', media_key='old', media_slots=['video'])]
        index = {'assets': {'a': {}}}
        apply_flyers(rows, index)
        expected = [dict(rows[0])]
        apply_flyers(rows, index)
        self.assertEqual(rows, expected)
        apply_flyers(rows, {'assets': {}})
        self.assertNotIn('media_slots', rows[0])


if __name__ == '__main__':
    unittest.main()
