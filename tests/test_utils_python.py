import functools
import gc
import operator
import platform
import unittest
from itertools import count
from warnings import catch_warnings

from scrapy.utils.python import (
    binary_is_text,
    dataclass_asdict,
    equal_attributes,
    get_func_args,
    is_dataclass_instance,
    memoizemethod_noargs,
    MutableChain,
    to_bytes,
    to_unicode,
    WeakKeyCache,
    without_none_values,
)


try:
    from dataclasses import make_dataclass
except ImportError:
    make_dataclass = None


__doctests__ = ['scrapy.utils.python']


class MutableChainTest(unittest.TestCase):
    def test_mutablechain(self):
        m = MutableChain(range(2), [2, 3], (4, 5))
        m.extend(range(6, 7))
        m.extend([7, 8])
        m.extend([9, 10], (11, 12))
        self.assertEqual(next(m), 0)
        self.assertEqual(m.__next__(), 1)
        with catch_warnings(record=True) as warnings:
            self.assertEqual(m.next(), 2)
            self.assertEqual(len(warnings), 1)
            self.assertIn('scrapy.utils.python.MutableChain.__next__',
                          str(warnings[0].message))
        self.assertEqual(list(m), list(range(3, 13)))


class ToUnicodeTest(unittest.TestCase):
    def test_converting_an_utf8_encoded_string_to_unicode(self):
        self.assertEqual(to_unicode(b'lel\xc3\xb1e'), u'lel\xf1e')

    def test_converting_a_latin_1_encoded_string_to_unicode(self):
        self.assertEqual(to_unicode(b'lel\xf1e', 'latin-1'), u'lel\xf1e')

    def test_converting_a_unicode_to_unicode_should_return_the_same_object(self):
        self.assertEqual(to_unicode(u'\xf1e\xf1e\xf1e'), u'\xf1e\xf1e\xf1e')

    def test_converting_a_strange_object_should_raise_TypeError(self):
        self.assertRaises(TypeError, to_unicode, 423)

    def test_errors_argument(self):
        self.assertEqual(
            to_unicode(b'a\xedb', 'utf-8', errors='replace'),
            u'a\ufffdb'
        )


class ToBytesTest(unittest.TestCase):
    def test_converting_a_unicode_object_to_an_utf_8_encoded_string(self):
        self.assertEqual(to_bytes(u'\xa3 49'), b'\xc2\xa3 49')

    def test_converting_a_unicode_object_to_a_latin_1_encoded_string(self):
        self.assertEqual(to_bytes(u'\xa3 49', 'latin-1'), b'\xa3 49')

    def test_converting_a_regular_bytes_to_bytes_should_return_the_same_object(self):
        self.assertEqual(to_bytes(b'lel\xf1e'), b'lel\xf1e')

    def test_converting_a_strange_object_should_raise_TypeError(self):
        self.assertRaises(TypeError, to_bytes, unittest)

    def test_errors_argument(self):
        self.assertEqual(
            to_bytes(u'a\ufffdb', 'latin-1', errors='replace'),
            b'a?b'
        )


class MemoizedMethodTest(unittest.TestCase):
    def test_memoizemethod_noargs(self):
        class A(object):

            @memoizemethod_noargs
            def cached(self):
                return object()

            def noncached(self):
                return object()

        a = A()
        one = a.cached()
        two = a.cached()
        three = a.noncached()
        assert one is two
        assert one is not three


class BinaryIsTextTest(unittest.TestCase):
    def test_binaryistext(self):
        assert binary_is_text(b"hello")

    def test_utf_16_strings_contain_null_bytes(self):
        assert binary_is_text(u"hello".encode('utf-16'))

    def test_one_with_encoding(self):
        assert binary_is_text(b"<div>Price \xa3</div>")

    def test_real_binary_bytes(self):
        assert not binary_is_text(b"\x02\xa3")


class UtilsPythonTestCase(unittest.TestCase):

    def test_equal_attributes(self):
        class Obj:
            pass

        a = Obj()
        b = Obj()
        # no attributes given return False
        self.assertFalse(equal_attributes(a, b, []))
        # not existent attributes
        self.assertFalse(equal_attributes(a, b, ['x', 'y']))

        a.x = 1
        b.x = 1
        # equal attribute
        self.assertTrue(equal_attributes(a, b, ['x']))

        b.y = 2
        # obj1 has no attribute y
        self.assertFalse(equal_attributes(a, b, ['x', 'y']))

        a.y = 2
        # equal attributes
        self.assertTrue(equal_attributes(a, b, ['x', 'y']))

        a.y = 1
        # differente attributes
        self.assertFalse(equal_attributes(a, b, ['x', 'y']))

        # test callable
        a.meta = {}
        b.meta = {}
        self.assertTrue(equal_attributes(a, b, ['meta']))

        # compare ['meta']['a']
        a.meta['z'] = 1
        b.meta['z'] = 1

        get_z = operator.itemgetter('z')
        get_meta = operator.attrgetter('meta')
        compare_z = lambda obj: get_z(get_meta(obj))

        self.assertTrue(equal_attributes(a, b, [compare_z, 'x']))
        # fail z equality
        a.meta['z'] = 2
        self.assertFalse(equal_attributes(a, b, [compare_z, 'x']))

    def test_weakkeycache(self):
        class _Weakme(object): pass
        _values = count()
        wk = WeakKeyCache(lambda k: next(_values))
        k = _Weakme()
        v = wk[k]
        self.assertEqual(v, wk[k])
        self.assertNotEqual(v, wk[_Weakme()])
        self.assertEqual(v, wk[k])
        del k
        for _ in range(100):
            if wk._weakdict:
                gc.collect()
        self.assertFalse(len(wk._weakdict))

    def test_get_func_args(self):
        def f1(a, b, c):
            pass

        def f2(a, b=None, c=None):
            pass

        class A(object):
            def __init__(self, a, b, c):
                pass

            def method(self, a, b, c):
                pass

        class Callable(object):

            def __call__(self, a, b, c):
                pass

        a = A(1, 2, 3)
        cal = Callable()
        partial_f1 = functools.partial(f1, None)
        partial_f2 = functools.partial(f1, b=None)
        partial_f3 = functools.partial(partial_f2, None)

        self.assertEqual(get_func_args(f1), ['a', 'b', 'c'])
        self.assertEqual(get_func_args(f2), ['a', 'b', 'c'])
        self.assertEqual(get_func_args(A), ['a', 'b', 'c'])
        self.assertEqual(get_func_args(a.method), ['a', 'b', 'c'])
        self.assertEqual(get_func_args(partial_f1), ['b', 'c'])
        self.assertEqual(get_func_args(partial_f2), ['a', 'c'])
        self.assertEqual(get_func_args(partial_f3), ['c'])
        self.assertEqual(get_func_args(cal), ['a', 'b', 'c'])
        self.assertEqual(get_func_args(object), [])

        if platform.python_implementation() == 'CPython':
            # TODO: how do we fix this to return the actual argument names?
            self.assertEqual(get_func_args(str.split), [])
            self.assertEqual(get_func_args(" ".join), [])
            self.assertEqual(get_func_args(operator.itemgetter(2)), [])
        else:
            self.assertEqual(
                get_func_args(str.split, stripself=True), ['sep', 'maxsplit'])
            self.assertEqual(get_func_args(" ".join, stripself=True), ['list'])
            self.assertEqual(
                get_func_args(operator.itemgetter(2), stripself=True), ['obj'])

    def test_without_none_values(self):
        self.assertEqual(without_none_values([1, None, 3, 4]), [1, 3, 4])
        self.assertEqual(without_none_values((1, None, 3, 4)), (1, 3, 4))
        self.assertEqual(
            without_none_values({'one': 1, 'none': None, 'three': 3, 'four': 4}),
            {'one': 1, 'three': 3, 'four': 4})


class DataclassItemsTestCase(unittest.TestCase):

    @unittest.skipIf(not make_dataclass, "dataclasses module is not available")
    def test_dataclasses_asdict(self):
        TestDataClass = make_dataclass(
            "TestDataClass",
            [("name", str), ("url", str), ("price", int)],
        )
        self.assertTrue(is_dataclass_instance(TestDataClass("Name", "URL", 10)))
        self.assertEqual(
            dataclass_asdict(TestDataClass("Name", "URL", 10)),
            dict(name="Name", url="URL", price=10)
        )

    @unittest.skipIf(make_dataclass, "dataclasses module is available")
    def test_dataclasses_importerror(self):
        self.assertFalse(is_dataclass_instance(object()))
        self.assertRaises(ImportError, dataclass_asdict, object())


if __name__ == "__main__":
    unittest.main()
