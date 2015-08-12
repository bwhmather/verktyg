"""
    verktyg.testsuite.test_datastructures
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests the functionality of the provided Verktyg datastructures.

    Classes prefixed with an underscore are mixins and are not discovered by
    the test runner.

    TODO:

    -   FileMultiDict
    -   Immutable types undertested
    -   Split up dict tests

    :copyright:
        (c) 2015 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.

"""
import unittest


import pickle
from contextlib import contextmanager
from copy import copy, deepcopy

from verktyg import datastructures
from verktyg.exceptions import BadRequestKeyError


class NativeItermethodsTestCase(unittest.TestCase):

    def test_basic(self):
        class StupidDict(object):

            def keys(self, multi=1):
                return iter(['a', 'b', 'c'] * multi)

            def values(self, multi=1):
                return iter([1, 2, 3] * multi)

            def items(self, multi=1):
                return iter(
                    zip(self.keys(multi=multi), self.values(multi=multi))
                )

        d = StupidDict()
        expected_keys = ['a', 'b', 'c']
        expected_values = [1, 2, 3]
        expected_items = list(zip(expected_keys, expected_values))

        self.assertEqual(list(d.keys()), expected_keys)
        self.assertEqual(list(d.values()), expected_values)
        self.assertEqual(list(d.items()), expected_items)

        self.assertEqual(list(d.keys(2)), expected_keys * 2)
        self.assertEqual(list(d.values(2)), expected_values * 2)
        self.assertEqual(list(d.items(2)), expected_items * 2)


class _MutableMultiDictTests(object):
    storage_class = None

    def test_pickle(self):
        cls = self.storage_class

        def create_instance(module=None):
            if module is None:
                d = cls()
            else:
                old = cls.__module__
                cls.__module__ = module
                d = cls()
                cls.__module__ = old
            d.setlist(b'foo', [1, 2, 3, 4])
            d.setlist(b'bar', b'foo bar baz'.split())
            return d

        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            d = create_instance()
            s = pickle.dumps(d, protocol)
            ud = pickle.loads(s)
            self.assertEqual(type(ud), type(d))
            self.assertEqual(ud, d)
            alternative = pickle.dumps(create_instance('verktyg'), protocol)
            self.assertEqual(pickle.loads(alternative), d)
            ud[b'newkey'] = b'bla'
            self.assertNotEqual(ud, d)

    def test_basic_interface(self):
        md = self.storage_class()
        self.assertIsInstance(md, dict)

        mapping = [('a', 1), ('b', 2), ('a', 2), ('d', 3),
                   ('a', 1), ('a', 3), ('d', 4), ('c', 3)]
        md = self.storage_class(mapping)

        # simple getitem gives the first value
        self.assertEqual(md['a'], 1)
        self.assertEqual(md['c'], 3)
        self.assertRaises(KeyError, lambda: md['e'])
        self.assertEqual(md.get('a'), 1)

        # list getitem
        self.assertEqual(md.getlist('a'), [1, 2, 1, 3])
        self.assertEqual(md.getlist('d'), [3, 4])
        # do not raise if key not found
        self.assertEqual(md.getlist('x'), [])

        # simple setitem overwrites all values
        md['a'] = 42
        self.assertEqual(md.getlist('a'), [42])

        # list setitem
        md.setlist('a', [1, 2, 3])
        self.assertEqual(md['a'], 1)
        self.assertEqual(md.getlist('a'), [1, 2, 3])

        # verify that it does not change original lists
        l1 = [1, 2, 3]
        md.setlist('a', l1)
        del l1[:]
        self.assertEqual(md['a'], 1)

        # setdefault, setlistdefault
        self.assertEqual(md.setdefault('u', 23), 23)
        self.assertEqual(md.getlist('u'), [23])
        del md['u']

        md.setlist('u', [-1, -2])

        # delitem
        del md['u']
        self.assertRaises(KeyError, lambda: md['u'])
        del md['d']
        self.assertEqual(md.getlist('d'), [])

        # keys, values, items, lists
        self.assertEqual(list(sorted(md.keys())), ['a', 'b', 'c'])
        self.assertEqual(list(sorted(md.values())), [1, 2, 3])
        self.assertEqual(
            list(sorted(md.items())),
            [('a', 1), ('b', 2), ('c', 3)]
        )
        self.assertEqual(
            list(sorted(md.items(multi=True))),
            [('a', 1), ('a', 2), ('a', 3), ('b', 2), ('c', 3)]
        )
        self.assertEqual(
            list(sorted(md.lists())),
            [('a', [1, 2, 3]), ('b', [2]), ('c', [3])]
        )

        # copy method
        c = md.copy()
        self.assertEqual(c['a'], 1)
        self.assertEqual(c.getlist('a'), [1, 2, 3])

        # copy method 2
        c = copy(md)
        self.assertEqual(c['a'], 1)
        self.assertEqual(c.getlist('a'), [1, 2, 3])

        # deepcopy method
        c = md.deepcopy()
        self.assertEqual(c['a'], 1)
        self.assertEqual(c.getlist('a'), [1, 2, 3])

        # deepcopy method 2
        c = deepcopy(md)
        self.assertEqual(c['a'], 1)
        self.assertEqual(c.getlist('a'), [1, 2, 3])

        # update with a multidict
        od = self.storage_class([('a', 4), ('a', 5), ('y', 0)])
        md.update(od)
        self.assertEqual(md.getlist('a'), [1, 2, 3, 4, 5])
        self.assertEqual(md.getlist('y'), [0])

        # update with a regular dict
        md = c
        od = {'a': 4, 'y': 0}
        md.update(od)
        self.assertEqual(md.getlist('a'), [1, 2, 3, 4])
        self.assertEqual(md.getlist('y'), [0])

        # pop, poplist, popitem, popitemlist
        self.assertEqual(md.pop('y'), 0)
        self.assertNotIn('y', md)
        self.assertEqual(md.poplist('a'), [1, 2, 3, 4])
        self.assertNotIn('a', md)
        self.assertEqual(md.poplist('missing'), [])

        # remaining: b=2, c=3
        popped = md.popitem()
        self.assertIn(popped, [('b', 2), ('c', 3)])
        popped = md.popitemlist()
        self.assertIn(popped, [('b', [2]), ('c', [3])])

        # type conversion
        md = self.storage_class({'a': '4', 'b': ['2', '3']})
        self.assertEqual(md.get('a', type=int), 4)
        self.assertEqual(md.getlist('b', type=int), [2, 3])

        # repr
        md = self.storage_class([('a', 1), ('a', 2), ('b', 3)])
        self.assertIn("('a', 1)", repr(md))
        self.assertIn("('a', 2)", repr(md))
        self.assertIn("('b', 3)", repr(md))

        # add and getlist
        md.add('c', '42')
        md.add('c', '23')
        self.assertEqual(md.getlist('c'), ['42', '23'])
        md.add('c', 'blah')
        self.assertEqual(md.getlist('c', type=int), [42, 23])

        # setdefault
        md = self.storage_class()
        md.setdefault('x', []).append(42)
        md.setdefault('x', []).append(23)
        self.assertEqual(md['x'], [42, 23])

        # to dict
        md = self.storage_class()
        md['foo'] = 42
        md.add('bar', 1)
        md.add('bar', 2)
        self.assertEqual(md.to_dict(), {'foo': 42, 'bar': 1})
        self.assertEqual(md.to_dict(flat=False), {'foo': [42], 'bar': [1, 2]})

        # popitem from empty dict
        self.assertRaises(KeyError, self.storage_class().popitem)

        self.assertRaises(KeyError, self.storage_class().popitemlist)

        # key errors are of a special type
        self.assertRaises(BadRequestKeyError, lambda: self.storage_class()[42])

        # setlist works
        md = self.storage_class()
        md['foo'] = 42
        md.setlist('foo', [1, 2])
        self.assertEqual(md.getlist('foo'), [1, 2])


class _ImmutableDictTests(object):
    storage_class = None

    def test_follows_dict_interface(self):
        cls = self.storage_class

        data = {'foo': 1, 'bar': 2, 'baz': 3}
        d = cls(data)

        self.assertEqual(d['foo'], 1)
        self.assertEqual(d['bar'], 2)
        self.assertEqual(d['baz'], 3)
        self.assertEqual(sorted(d.keys()), ['bar', 'baz', 'foo'])
        self.assertIn('foo', d)
        self.assertNotIn('foox', d)
        self.assertEqual(len(d), 3)

    def test_copies_are_mutable(self):
        cls = self.storage_class
        immutable = cls({'a': 1})
        self.assertRaises(TypeError, immutable.pop, 'a')

        mutable = immutable.copy()
        mutable.pop('a')
        self.assertIn('a', immutable)
        self.assertIsNot(mutable, immutable)
        self.assertIs(copy(immutable), immutable)

    def test_dict_is_hashable(self):
        cls = self.storage_class
        immutable = cls({'a': 1, 'b': 2})
        immutable2 = cls({'a': 2, 'b': 2})
        x = set([immutable])
        self.assertIn(immutable, x)
        self.assertNotIn(immutable2, x)
        x.discard(immutable)
        self.assertNotIn(immutable, x)
        self.assertNotIn(immutable2, x)
        x.add(immutable2)
        self.assertNotIn(immutable, x)
        self.assertIn(immutable2, x)
        x.add(immutable)
        self.assertIn(immutable, x)
        self.assertIn(immutable2, x)


class ImmutableTypeConversionDictTestCase(
            _ImmutableDictTests, unittest.TestCase
        ):
    storage_class = datastructures.ImmutableTypeConversionDict


class ImmutableMultiDictTestCase(_ImmutableDictTests, unittest.TestCase):
    storage_class = datastructures.ImmutableMultiDict

    def test_multidict_is_hashable(self):
        cls = self.storage_class
        immutable = cls({'a': [1, 2], 'b': 2})
        immutable2 = cls({'a': [1], 'b': 2})
        x = set([immutable])
        self.assertIn(immutable, x)
        self.assertNotIn(immutable2, x)
        x.discard(immutable)
        self.assertNotIn(immutable, x)
        self.assertNotIn(immutable2, x)
        x.add(immutable2)
        self.assertNotIn(immutable, x)
        self.assertIn(immutable2, x)
        x.add(immutable)
        self.assertIn(immutable, x)
        self.assertIn(immutable2, x)


class ImmutableDictTestCase(_ImmutableDictTests, unittest.TestCase):
    storage_class = datastructures.ImmutableDict


class ImmutableOrderedMultiDictTestCase(
            _ImmutableDictTests, unittest.TestCase
        ):
    storage_class = datastructures.ImmutableOrderedMultiDict

    def test_ordered_multidict_is_hashable(self):
        a = self.storage_class([('a', 1), ('b', 1), ('a', 2)])
        b = self.storage_class([('a', 1), ('a', 2), ('b', 1)])
        self.assertNotEqual(hash(a), hash(b))


class MultiDictTestCase(_MutableMultiDictTests, unittest.TestCase):
    storage_class = datastructures.MultiDict

    def test_multidict_pop(self):
        def make_d():
            return self.storage_class({'foo': [1, 2, 3, 4]})
        d = make_d()
        self.assertEqual(d.pop('foo'), 1)
        self.assertFalse(d)
        d = make_d()
        self.assertEqual(d.pop('foo', 32), 1)
        self.assertFalse(d)
        d = make_d()
        self.assertEqual(d.pop('foos', 32), 32)
        self.assertTrue(d)

        self.assertRaises(KeyError, d.pop, 'foos')

    def test_setlistdefault(self):
        md = self.storage_class()
        self.assertEqual(md.setlistdefault('u', [-1, -2]), [-1, -2])
        self.assertEqual(md.getlist('u'), [-1, -2])
        self.assertEqual(md['u'], -1)

    def test_iter_interfaces(self):
        mapping = [
            ('a', 1), ('b', 2), ('a', 2), ('d', 3),
            ('a', 1), ('a', 3), ('d', 4), ('c', 3),
        ]
        md = self.storage_class(mapping)
        self.assertEqual(
            list(zip(md.keys(), md.listvalues())), list(md.lists())
        )
        self.assertEqual(
            list(zip(md, md.listvalues())), list(md.lists())
        )
        self.assertEqual(
            list(zip(md.keys(), md.listvalues())), list(md.lists())
        )


class OrderedMultiDictTestCase(_MutableMultiDictTests, unittest.TestCase):
    storage_class = datastructures.OrderedMultiDict

    def test_ordered_interface(self):
        cls = self.storage_class

        d = cls()
        self.assertFalse(d)
        d.add('foo', 'bar')
        self.assertEqual(len(d), 1)
        d.add('foo', 'baz')
        self.assertEqual(len(d), 1)
        self.assertEqual(list(d.items()), [('foo', 'bar')])
        self.assertEqual(list(d), ['foo'])
        self.assertEqual(
            list(d.items(multi=True)), [('foo', 'bar'), ('foo', 'baz')]
        )
        del d['foo']
        self.assertFalse(d)
        self.assertEqual(len(d), 0)
        self.assertEqual(list(d), [])

        d.update([('foo', 1), ('foo', 2), ('bar', 42)])
        d.add('foo', 3)
        self.assertEqual(d.getlist('foo'), [1, 2, 3])
        self.assertEqual(d.getlist('bar'), [42])
        self.assertEqual(list(d.items()), [('foo', 1), ('bar', 42)])

        expected = ['foo', 'bar']

        self.assertEqual(list(d.keys()), expected)
        self.assertEqual(list(d), expected)
        self.assertEqual(list(d.keys()), expected)

        self.assertEqual(list(d.items(multi=True)), [
            ('foo', 1), ('foo', 2), ('bar', 42), ('foo', 3),
        ])
        self.assertEqual(len(d), 2)

        self.assertEqual(d.pop('foo'), 1)
        self.assertIs(d.pop('blafasel', None), None)
        self.assertEqual(d.pop('blafasel', 42), 42)
        self.assertEqual(len(d), 1)
        self.assertEqual(d.poplist('bar'), [42])
        self.assertFalse(d)

        d.get('missingkey') is None

        d.add('foo', 42)
        d.add('foo', 23)
        d.add('bar', 2)
        d.add('foo', 42)
        self.assertEqual(d, datastructures.MultiDict(d))
        id = self.storage_class(d)
        self.assertEqual(d, id)
        d.add('foo', 2)
        self.assertNotEqual(d, id)

        d.update({'blah': [1, 2, 3]})
        self.assertEqual(d['blah'], 1)
        self.assertEqual(d.getlist('blah'), [1, 2, 3])

        # setlist works
        d = self.storage_class()
        d['foo'] = 42
        d.setlist('foo', [1, 2])
        self.assertEqual(d.getlist('foo'), [1, 2])

        self.assertRaises(BadRequestKeyError, d.pop, 'missing')
        self.assertRaises(BadRequestKeyError, lambda: d['missing'])

        # popping
        d = self.storage_class()
        d.add('foo', 23)
        d.add('foo', 42)
        d.add('foo', 1)
        self.assertEqual(d.popitem(), ('foo', 23))
        self.assertRaises(BadRequestKeyError, d.popitem)
        self.assertFalse(d)

        d.add('foo', 23)
        d.add('foo', 42)
        d.add('foo', 1)
        self.assertEqual(d.popitemlist(), ('foo', [23, 42, 1]))

        self.assertRaises(BadRequestKeyError, d.popitemlist)

    def test_iterables(self):
        a = datastructures.MultiDict((("key_a", "value_a"),))
        b = datastructures.MultiDict((("key_b", "value_b"),))
        ab = datastructures.CombinedMultiDict((a, b))

        self.assertEqual(sorted(ab.lists()), [
            ('key_a', ['value_a']), ('key_b', ['value_b']),
        ])
        self.assertEqual(sorted(ab.listvalues()), [['value_a'], ['value_b']])
        self.assertEqual(sorted(ab.keys()), ["key_a", "key_b"])


class CombinedMultiDictTestCase(unittest.TestCase):
    storage_class = datastructures.CombinedMultiDict

    def test_basic_interface(self):
        d1 = datastructures.MultiDict([('foo', '1')])
        d2 = datastructures.MultiDict([('bar', '2'), ('bar', '3')])
        d = self.storage_class([d1, d2])

        # lookup
        self.assertEqual(d['foo'], '1')
        self.assertEqual(d['bar'], '2')
        self.assertEqual(d.getlist('bar'), ['2', '3'])

        self.assertEqual(sorted(d.items()), [('bar', '2'), ('foo', '1')])
        self.assertEqual(
            sorted(d.items(multi=True)),
            [('bar', '2'), ('bar', '3'), ('foo', '1')]
        )
        self.assertNotIn('missingkey', d)
        self.assertIn('foo', d)

        # type lookup
        self.assertEqual(d.get('foo', type=int), 1)
        self.assertEqual(d.getlist('bar', type=int), [2, 3])

        # get key errors for missing stuff
        self.assertRaises(KeyError, lambda: d['missing'])

        # make sure that they are immutable
        try:
            d['foo'] = 'blub'
        except TypeError:
            pass
        else:
            self.fail()

        # copies are immutable
        d = d.copy()
        try:
            d['foo'] = 'blub'
        except TypeError:
            pass
        else:
            self.fail()

        # make sure lists merges
        md1 = datastructures.MultiDict((("foo", "bar"),))
        md2 = datastructures.MultiDict((("foo", "blafasel"),))
        x = self.storage_class((md1, md2))
        self.assertEqual(list(x.lists()), [('foo', ['bar', 'blafasel'])])

    def test_length(self):
        d1 = datastructures.MultiDict([('foo', '1')])
        d2 = datastructures.MultiDict([('bar', '2')])
        self.assertEqual(len(d1) == len(d2), 1)
        d = self.storage_class([d1, d2])
        self.assertEqual(len(d), 2)
        d1.clear()
        self.assertEqual(len(d1), 0)
        self.assertEqual(len(d), 1)


class ImmutableListTestCase(unittest.TestCase):
    storage_class = datastructures.ImmutableList

    def test_list_hashable(self):
        t = (1, 2, 3, 4)
        l = self.storage_class(t)
        self.assertEqual(hash(t), hash(l))
        self.assertNotEqual(t, l)


def make_call_asserter(func=None):
    """Utility to assert a certain number of function calls.

    :param func: Additional callback for each function call.

    >>> assert_calls, func = make_call_asserter()
    >>> with assert_calls(2):
            func()
            func()
    """

    calls = 0

    @contextmanager
    def asserter(count, msg=None):
        nonlocal calls
        calls = 0
        yield
        assert calls == count

    def wrapped(*args, **kwargs):
        nonlocal calls
        calls += 1
        if func is not None:
            return func(*args, **kwargs)

    return asserter, wrapped


class CallbackDictTestCase(unittest.TestCase):
    storage_class = datastructures.CallbackDict

    def test_callback_dict_reads(self):
        assert_calls, func = make_call_asserter()
        initial = {'a': 'foo', 'b': 'bar'}
        dct = self.storage_class(initial=initial, on_update=func)
        with assert_calls(0, 'callback triggered by read-only method'):
            # read-only methods
            dct['a']
            dct.get('a')
            self.assertRaises(KeyError, lambda: dct['x'])
            'a' in dct
            list(iter(dct))
            dct.copy()
        with assert_calls(0, 'callback triggered without modification'):
            # methods that may write but don't
            dct.pop('z', None)
            dct.setdefault('a')

    def test_callback_dict_writes(self):
        assert_calls, func = make_call_asserter()
        initial = {'a': 'foo', 'b': 'bar'}
        dct = self.storage_class(initial=initial, on_update=func)
        with assert_calls(8, 'callback not triggered by write method'):
            # always-write methods
            dct['z'] = 123
            dct['z'] = 123  # must trigger again
            del dct['z']
            dct.pop('b', None)
            dct.setdefault('x')
            dct.popitem()
            dct.update([])
            dct.clear()
        with assert_calls(0, 'callback triggered by failed del'):
            self.assertRaises(KeyError, lambda: dct.__delitem__('x'))
        with assert_calls(0, 'callback triggered by failed pop'):
            self.assertRaises(KeyError, lambda: dct.pop('x'))
