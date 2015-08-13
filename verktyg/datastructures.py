"""
    verktyg.datastructures
    ~~~~~~~~~~~~~~~~~~~~~~

    This module provides mixins and classes with an immutable interface.

    :copyright:
        (c) 2015 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import re
from copy import deepcopy
from itertools import repeat

from werkzeug._internal import _missing
from verktyg import exceptions


_locale_delim_re = re.compile(r'[_-]')


def is_immutable(self):
    raise TypeError('%r objects are immutable' % self.__class__.__name__)


def iter_multi_items(mapping):
    """Iterates over the items of a mapping yielding keys and values
    without dropping any from more complex structures.
    """
    if isinstance(mapping, MultiDict):
        for item in mapping.items(multi=True):
            yield item
    elif isinstance(mapping, dict):
        for key, value in mapping.items():
            if isinstance(value, (tuple, list)):
                for value in value:
                    yield key, value
            else:
                yield key, value
    else:
        for item in mapping:
            yield item


class ImmutableListMixin(object):
    """Makes a :class:`list` immutable.

    :private:
    """

    _hash_cache = None

    def __hash__(self):
        if self._hash_cache is not None:
            return self._hash_cache
        rv = self._hash_cache = hash(tuple(self))
        return rv

    def __reduce_ex__(self, protocol):
        return type(self), (list(self),)

    def __delitem__(self, key):
        is_immutable(self)

    def __delslice__(self, i, j):
        is_immutable(self)

    def __iadd__(self, other):
        is_immutable(self)
    __imul__ = __iadd__

    def __setitem__(self, key, value):
        is_immutable(self)

    def __setslice__(self, i, j, value):
        is_immutable(self)

    def append(self, item):
        is_immutable(self)
    remove = append

    def extend(self, iterable):
        is_immutable(self)

    def insert(self, pos, value):
        is_immutable(self)

    def pop(self, index=-1):
        is_immutable(self)

    def reverse(self):
        is_immutable(self)

    def sort(self, cmp=None, key=None, reverse=None):
        is_immutable(self)


class ImmutableList(ImmutableListMixin, list):
    """An immutable :class:`list`.

    :private:
    """

    def __repr__(self):
        return '%s(%s)' % (
            self.__class__.__name__,
            list.__repr__(self),
        )


class ImmutableDictMixin(object):
    """Makes a :class:`dict` immutable.

    :private:
    """
    _hash_cache = None

    @classmethod
    def fromkeys(cls, keys, value=None):
        instance = super(cls, cls).__new__(cls)
        instance.__init__(zip(keys, repeat(value)))
        return instance

    def __reduce_ex__(self, protocol):
        return type(self), (dict(self),)

    def _iter_hashitems(self):
        return self.items()

    def __hash__(self):
        if self._hash_cache is not None:
            return self._hash_cache
        rv = self._hash_cache = hash(frozenset(self._iter_hashitems()))
        return rv

    def setdefault(self, key, default=None):
        is_immutable(self)

    def update(self, *args, **kwargs):
        is_immutable(self)

    def pop(self, key, default=None):
        is_immutable(self)

    def popitem(self):
        is_immutable(self)

    def __setitem__(self, key, value):
        is_immutable(self)

    def __delitem__(self, key):
        is_immutable(self)

    def clear(self):
        is_immutable(self)


class ImmutableMultiDictMixin(ImmutableDictMixin):
    """Makes a :class:`MultiDict` immutable.

    :private:
    """

    def __reduce_ex__(self, protocol):
        return type(self), (list(self.items(multi=True)),)

    def _iter_hashitems(self):
        return self.items(multi=True)

    def add(self, key, value):
        is_immutable(self)

    def popitemlist(self):
        is_immutable(self)

    def poplist(self, key):
        is_immutable(self)

    def setlist(self, key, new_list):
        is_immutable(self)

    def setlistdefault(self, key, default_list=None):
        is_immutable(self)


class UpdateDictMixin(object):
    """Makes dicts call `self.on_update` on modifications.

    :private:
    """

    on_update = None

    def calls_update(name):
        def oncall(self, *args, **kw):
            rv = getattr(super(UpdateDictMixin, self), name)(*args, **kw)
            if self.on_update is not None:
                self.on_update(self)
            return rv
        oncall.__name__ = name
        return oncall

    def setdefault(self, key, default=None):
        modified = key not in self
        rv = super(UpdateDictMixin, self).setdefault(key, default)
        if modified and self.on_update is not None:
            self.on_update(self)
        return rv

    def pop(self, key, default=_missing):
        modified = key in self
        if default is _missing:
            rv = super(UpdateDictMixin, self).pop(key)
        else:
            rv = super(UpdateDictMixin, self).pop(key, default)
        if modified and self.on_update is not None:
            self.on_update(self)
        return rv

    __setitem__ = calls_update('__setitem__')
    __delitem__ = calls_update('__delitem__')
    clear = calls_update('clear')
    popitem = calls_update('popitem')
    update = calls_update('update')
    del calls_update


class TypeConversionDict(dict):
    """Works like a regular dict but the :meth:`get` method can perform
    type conversions.  :class:`MultiDict` and :class:`CombinedMultiDict`
    are subclasses of this class and provide the same feature.
    """

    def get(self, key, default=None, type=None):
        """Return the default value if the requested data doesn't exist.
        If `type` is provided and is a callable it should convert the value,
        return it or raise a :exc:`ValueError` if that is not possible.  In
        this case the function will return the default as if the value was not
        found:

        >>> d = TypeConversionDict(foo='42', bar='blub')
        >>> d.get('foo', type=int)
        42
        >>> d.get('bar', -1, type=int)
        -1

        :param key:
            The key to be looked up.
        :param default:
            The default value to be returned if the key can't be looked up.  If
            not further specified `None` is returned.
        :param type:
            A callable that is used to cast the value in the
            :class:`MultiDict`.  If a :exc:`ValueError` is raised by this
            callable the default value is returned.
        """
        try:
            rv = self[key]
            if type is not None:
                rv = type(rv)
        except (KeyError, ValueError):
            rv = default
        return rv


class ImmutableTypeConversionDict(ImmutableDictMixin, TypeConversionDict):
    """Works like a :class:`TypeConversionDict` but does not support
    modifications.
    """

    def copy(self):
        """Return a shallow mutable copy of this object.  Keep in mind that
        the standard library's :func:`copy` function is a no-op for this class
        like for any other python immutable type (eg: :class:`tuple`).
        """
        return TypeConversionDict(self)

    def __copy__(self):
        return self


class MultiDict(TypeConversionDict):
    """A :class:`MultiDict` is a dictionary subclass customized to deal with
    multiple values for the same key which is for example used by the parsing
    functions in the wrappers.  This is necessary because some HTML form
    elements pass multiple values for the same key.

    :class:`MultiDict` implements all standard dictionary methods.
    Internally, it saves all values for a key as a list, but the standard dict
    access methods will only return the first value for a key. If you want to
    gain access to the other values, too, you have to use the `list` methods as
    explained below.

    Basic Usage:

    >>> d = MultiDict([('a', 'b'), ('a', 'c')])
    >>> d
    MultiDict([('a', 'b'), ('a', 'c')])
    >>> d['a']
    'b'
    >>> d.getlist('a')
    ['b', 'c']
    >>> 'a' in d
    True

    It behaves like a normal dict thus all dict functions will only return the
    first value when multiple values for one key are found.

    From Werkzeug 0.3 onwards, the `KeyError` raised by this class is also a
    subclass of the :exc:`~exceptions.BadRequest` HTTP exception and will
    render a page for a ``400 BAD REQUEST`` if caught in a catch-all for HTTP
    exceptions.

    A :class:`MultiDict` can be constructed from an iterable of
    ``(key, value)`` tuples, a dict, a :class:`MultiDict` or from Werkzeug 0.2
    onwards some keyword parameters.

    :param mapping:
        the initial value for the :class:`MultiDict`.  Either a regular dict,
        an iterable of ``(key, value)`` tuples or `None`.
    """

    def __init__(self, mapping=None):
        if isinstance(mapping, MultiDict):
            dict.__init__(self, ((k, l[:]) for k, l in mapping.lists()))
        elif isinstance(mapping, dict):
            tmp = {}
            for key, value in mapping.items():
                if isinstance(value, (tuple, list)):
                    value = list(value)
                else:
                    value = [value]
                tmp[key] = value
            dict.__init__(self, tmp)
        else:
            tmp = {}
            for key, value in mapping or ():
                tmp.setdefault(key, []).append(value)
            dict.__init__(self, tmp)

    def __getstate__(self):
        return dict(self.lists())

    def __setstate__(self, value):
        dict.clear(self)
        dict.update(self, value)

    def __getitem__(self, key):
        """Return the first data value for this key;
        raises KeyError if not found.

        :param key:
            The key to be looked up.
        :raise KeyError:
            If the key does not exist.
        """
        if key in self:
            return dict.__getitem__(self, key)[0]
        raise exceptions.BadRequestKeyError(key)

    def __setitem__(self, key, value):
        """Like :meth:`add` but removes an existing key first.

        :param key:
            the key for the value.
        :param value:
            the value to set.
        """
        dict.__setitem__(self, key, [value])

    def add(self, key, value):
        """Adds a new value for the key.

        :param key:
            The key for the value.
        :param value:
            The value to add.
        """
        dict.setdefault(self, key, []).append(value)

    def getlist(self, key, type=None):
        """Return the list of items for a given key. If that key is not in the
        `MultiDict`, the return value will be an empty list.  Just as `get`
        `getlist` accepts a `type` parameter.  All items will be converted
        with the callable defined there.

        :param key:
            The key to be looked up.
        :param type:
            A callable that is used to cast the value in the
            :class:`MultiDict`.  If a :exc:`ValueError` is raised by this
            callable the value will be removed from the list.
        :return: a :class:`list` of all the values for the key.
        """
        try:
            rv = dict.__getitem__(self, key)
        except KeyError:
            return []
        if type is None:
            return list(rv)
        result = []
        for item in rv:
            try:
                result.append(type(item))
            except ValueError:
                pass
        return result

    def setlist(self, key, new_list):
        """Remove the old values for a key and add new ones.  Note that the list
        you pass the values in will be shallow-copied before it is inserted in
        the dictionary.

        >>> d = MultiDict()
        >>> d.setlist('foo', ['1', '2'])
        >>> d['foo']
        '1'
        >>> d.getlist('foo')
        ['1', '2']

        :param key:
            The key for which the values are set.
        :param new_list:
            An iterable with the new values for the key.  Old values are
            removed first.
        """
        dict.__setitem__(self, key, list(new_list))

    def setdefault(self, key, default=None):
        """Returns the value for the key if it is in the dict, otherwise it
        returns `default` and sets that value for `key`.

        :param key:
            The key to be looked up.
        :param default:
            The default value to be returned if the key is not in the dict.  If
            not further specified it's `None`.
        """
        if key not in self:
            self[key] = default
        else:
            default = self[key]
        return default

    def setlistdefault(self, key, default_list=None):
        """Like `setdefault` but sets multiple values.  The list returned
        is not a copy, but the list that is actually used internally.  This
        means that you can put new values into the dict by appending items
        to the list:

        >>> d = MultiDict({"foo": 1})
        >>> d.setlistdefault("foo").extend([2, 3])
        >>> d.getlist("foo")
        [1, 2, 3]

        :param key:
            The key to be looked up.
        :param default:
            An iterable of default values.  It is either copied (in case it was
            a list) or converted into a list before returned.
        :return:
            a :class:`list`
        """
        if key not in self:
            default_list = list(default_list or ())
            dict.__setitem__(self, key, default_list)
        else:
            default_list = dict.__getitem__(self, key)
        return default_list

    def items(self, multi=False):
        """Return an iterator of ``(key, value)`` pairs.

        :param multi:
            If set to `True` the iterator returned will have a pair for each
            value of each key.  Otherwise it will only contain pairs for the
            first value of each key.
        """

        for key, values in dict.items(self):
            if multi:
                for value in values:
                    yield key, value
            else:
                yield key, values[0]

    def lists(self):
        """Return a list of ``(key, values)`` pairs, where values is the list
        of all values associated with the key."""

        for key, values in dict.items(self):
            yield key, list(values)

    def keys(self):
        return dict.keys(self)

    def __iter__(self):
        return iter(self.keys())

    def values(self):
        """Returns an iterator of the first value on every key's value list."""
        for values in dict.values(self):
            yield values[0]

    def listvalues(self):
        """Return an iterator of all values associated with a key.  Zipping
        :meth:`keys` and this is the same as calling :meth:`lists`:

        >>> d = MultiDict({"foo": [1, 2, 3]})
        >>> zip(d.keys(), d.listvalues()) == d.lists()
        True
        """

        return dict.values(self)

    def copy(self):
        """Return a shallow copy of this object."""
        return self.__class__(self)

    def deepcopy(self, memo=None):
        """Return a deep copy of this object."""
        return self.__class__(deepcopy(self.to_dict(flat=False), memo))

    def to_dict(self, flat=True):
        """Return the contents as regular dict.  If `flat` is `True` the
        returned dict will only have the first item present, if `flat` is
        `False` all values will be returned as lists.

        :param flat:
            If set to `False` the dict returned will have lists with all the
            values in it.  Otherwise it will only contain the first value for
            each key.
        :return:
            A :class:`dict`
        """
        if flat:
            return dict(self.items())
        return dict(self.lists())

    def update(self, other_dict):
        """update() extends rather than replaces existing key lists."""
        for key, value in iter_multi_items(other_dict):
            MultiDict.add(self, key, value)

    def pop(self, key, default=_missing):
        """Pop the first item for a list on the dict.  Afterwards the
        key is removed from the dict, so additional values are discarded:

        >>> d = MultiDict({"foo": [1, 2, 3]})
        >>> d.pop("foo")
        1
        >>> "foo" in d
        False

        :param key:
            The key to pop.
        :param default:
            If provided the value to return if the key was not in the
            dictionary.
        """
        try:
            return dict.pop(self, key)[0]
        except KeyError as e:
            if default is not _missing:
                return default
            raise exceptions.BadRequestKeyError(str(e))

    def popitem(self):
        """Pop an item from the dict."""
        try:
            item = dict.popitem(self)
            return (item[0], item[1][0])
        except KeyError as e:
            raise exceptions.BadRequestKeyError(str(e))

    def poplist(self, key):
        """Pop the list for a key from the dict.  If the key is not in the dict
        an empty list is returned.
        """
        return dict.pop(self, key, [])

    def popitemlist(self):
        """Pop a ``(key, list)`` tuple from the dict."""
        try:
            return dict.popitem(self)
        except KeyError as e:
            raise exceptions.BadRequestKeyError(str(e))

    def __copy__(self):
        return self.copy()

    def __deepcopy__(self, memo):
        return self.deepcopy(memo=memo)

    def __repr__(self):
        return '%s(%r)' % (
            self.__class__.__name__, list(self.items(multi=True))
        )


class _omd_bucket(object):
    """Wraps values in the :class:`OrderedMultiDict`.  This makes it
    possible to keep an order over multiple different keys.  It requires
    a lot of extra memory and slows down access a lot, but makes it
    possible to access elements in O(1) and iterate in O(n).
    """
    __slots__ = ('prev', 'key', 'value', 'next')

    def __init__(self, omd, key, value):
        self.prev = omd._last_bucket
        self.key = key
        self.value = value
        self.next = None

        if omd._first_bucket is None:
            omd._first_bucket = self
        if omd._last_bucket is not None:
            omd._last_bucket.next = self
        omd._last_bucket = self

    def unlink(self, omd):
        if self.prev:
            self.prev.next = self.next
        if self.next:
            self.next.prev = self.prev
        if omd._first_bucket is self:
            omd._first_bucket = self.next
        if omd._last_bucket is self:
            omd._last_bucket = self.prev


class OrderedMultiDict(MultiDict):
    """Works like a regular :class:`MultiDict` but preserves the
    order of the fields.  To convert the ordered multi dict into a
    list you can use the :meth:`items` method and pass it ``multi=True``.

    In general an :class:`OrderedMultiDict` is an order of magnitude
    slower than a :class:`MultiDict`.

    .. admonition:: note

       Due to a limitation in Python you cannot convert an ordered
       multi dict into a regular dict by using ``dict(multidict)``.
       Instead you have to use the :meth:`to_dict` method, otherwise
       the internal bucket objects are exposed.
    """

    def __init__(self, mapping=None):
        dict.__init__(self)
        self._first_bucket = self._last_bucket = None
        if mapping is not None:
            OrderedMultiDict.update(self, mapping)

    def __eq__(self, other):
        if not isinstance(other, MultiDict):
            return NotImplemented
        if isinstance(other, OrderedMultiDict):
            iter1 = self.items(multi=True)
            iter2 = other.items(multi=True)
            try:
                for k1, v1 in iter1:
                    k2, v2 = next(iter2)
                    if k1 != k2 or v1 != v2:
                        return False
            except StopIteration:
                return False
            try:
                next(iter2)
            except StopIteration:
                return True
            return False
        if len(self) != len(other):
            return False
        for key, values in self.lists():
            if other.getlist(key) != values:
                return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def __reduce_ex__(self, protocol):
        return type(self), (list(self.items(multi=True)),)

    def __getstate__(self):
        return list(self.items(multi=True))

    def __setstate__(self, values):
        dict.clear(self)
        for key, value in values:
            self.add(key, value)

    def __getitem__(self, key):
        if key in self:
            return dict.__getitem__(self, key)[0].value
        raise exceptions.BadRequestKeyError(key)

    def __setitem__(self, key, value):
        self.poplist(key)
        self.add(key, value)

    def __delitem__(self, key):
        self.pop(key)

    def keys(self):
        return (key for key, value in self.items())

    __iter__ = keys

    def values(self):
        return (value for key, value in self.items())

    def items(self, multi=False):
        ptr = self._first_bucket
        if multi:
            while ptr is not None:
                yield ptr.key, ptr.value
                ptr = ptr.next
        else:
            returned_keys = set()
            while ptr is not None:
                if ptr.key not in returned_keys:
                    returned_keys.add(ptr.key)
                    yield ptr.key, ptr.value
                ptr = ptr.next

    def lists(self):
        returned_keys = set()
        ptr = self._first_bucket
        while ptr is not None:
            if ptr.key not in returned_keys:
                yield ptr.key, self.getlist(ptr.key)
                returned_keys.add(ptr.key)
            ptr = ptr.next

    def listvalues(self):
        for key, values in self.lists():
            yield values

    def add(self, key, value):
        dict.setdefault(self, key, []).append(_omd_bucket(self, key, value))

    def getlist(self, key, type=None):
        try:
            rv = dict.__getitem__(self, key)
        except KeyError:
            return []
        if type is None:
            return [x.value for x in rv]
        result = []
        for item in rv:
            try:
                result.append(type(item.value))
            except ValueError:
                pass
        return result

    def setlist(self, key, new_list):
        self.poplist(key)
        for value in new_list:
            self.add(key, value)

    def setlistdefault(self, key, default_list=None):
        raise TypeError('setlistdefault is unsupported for '
                        'ordered multi dicts')

    def update(self, mapping):
        for key, value in iter_multi_items(mapping):
            OrderedMultiDict.add(self, key, value)

    def poplist(self, key):
        buckets = dict.pop(self, key, ())
        for bucket in buckets:
            bucket.unlink(self)
        return [x.value for x in buckets]

    def pop(self, key, default=_missing):
        try:
            buckets = dict.pop(self, key)
        except KeyError as e:
            if default is not _missing:
                return default
            raise exceptions.BadRequestKeyError(str(e))
        for bucket in buckets:
            bucket.unlink(self)
        return buckets[0].value

    def popitem(self):
        try:
            key, buckets = dict.popitem(self)
        except KeyError as e:
            raise exceptions.BadRequestKeyError(str(e))
        for bucket in buckets:
            bucket.unlink(self)
        return key, buckets[0].value

    def popitemlist(self):
        try:
            key, buckets = dict.popitem(self)
        except KeyError as e:
            raise exceptions.BadRequestKeyError(str(e))
        for bucket in buckets:
            bucket.unlink(self)
        return key, [x.value for x in buckets]


class CombinedMultiDict(ImmutableMultiDictMixin, MultiDict):
    """A read only :class:`MultiDict` that you can pass multiple :class:`MultiDict`
    instances as sequence and it will combine the return values of all wrapped
    dicts:

    >>> from verktyg.datastructures import CombinedMultiDict, MultiDict
    >>> post = MultiDict([('foo', 'bar')])
    >>> get = MultiDict([('blub', 'blah')])
    >>> combined = CombinedMultiDict([get, post])
    >>> combined['foo']
    'bar'
    >>> combined['blub']
    'blah'

    This works for all read operations and will raise a `TypeError` for
    methods that usually change data which isn't possible.

    From Werkzeug 0.3 onwards, the `KeyError` raised by this class is also a
    subclass of the :exc:`~exceptions.BadRequest` HTTP exception and will
    render a page for a ``400 BAD REQUEST`` if caught in a catch-all for HTTP
    exceptions.
    """

    def __reduce_ex__(self, protocol):
        return type(self), (self.dicts,)

    def __init__(self, dicts=None):
        self.dicts = dicts or []

    @classmethod
    def fromkeys(cls):
        raise TypeError('cannot create %r instances by fromkeys' %
                        cls.__name__)

    def __getitem__(self, key):
        for d in self.dicts:
            if key in d:
                return d[key]
        raise exceptions.BadRequestKeyError(key)

    def get(self, key, default=None, type=None):
        for d in self.dicts:
            if key in d:
                if type is not None:
                    try:
                        return type(d[key])
                    except ValueError:
                        continue
                return d[key]
        return default

    def getlist(self, key, type=None):
        rv = []
        for d in self.dicts:
            rv.extend(d.getlist(key, type))
        return rv

    def _keys_impl(self):
        """This function exists so __len__ can be implemented more efficiently,
        saving one list creation from an iterator.

        Using this for Python 2's ``dict.keys`` behavior would be useless since
        `dict.keys` in Python 2 returns a list, while we have a set here.
        """
        rv = set()
        for d in self.dicts:
            rv.update(d.keys())
        return rv

    def keys(self):
        return iter(self._keys_impl())

    __iter__ = keys

    def items(self, multi=False):
        found = set()
        for d in self.dicts:
            for key, value in d.items(multi):
                if multi:
                    yield key, value
                elif key not in found:
                    found.add(key)
                    yield key, value

    def values(self):
        for key, value in self.items():
            yield value

    def lists(self):
        rv = {}
        for d in self.dicts:
            for key, values in d.lists():
                rv.setdefault(key, []).extend(values)
        return rv.items()

    def listvalues(self):
        return (x[1] for x in self.lists())

    def copy(self):
        """Return a shallow copy of this object."""
        return self.__class__(self.dicts[:])

    def to_dict(self, flat=True):
        """Return the contents as regular dict.  If `flat` is `True` the
        returned dict will only have the first item present, if `flat` is
        `False` all values will be returned as lists.

        :param flat:
            If set to `False` the dict returned will have lists with all the
            values in it.  Otherwise it will only contain the first item for
            each key.
        :return:
            A :class:`dict`
        """
        rv = {}
        for d in reversed(self.dicts):
            rv.update(d.to_dict(flat))
        return rv

    def __len__(self):
        return len(self._keys_impl())

    def __contains__(self, key):
        for d in self.dicts:
            if key in d:
                return True
        return False

    has_key = __contains__

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.dicts)


class ImmutableDict(ImmutableDictMixin, dict):
    """An immutable :class:`dict`.
    """

    def __repr__(self):
        return '%s(%s)' % (
            self.__class__.__name__,
            dict.__repr__(self),
        )

    def copy(self):
        """Return a shallow mutable copy of this object.  Keep in mind that
        the standard library's :func:`copy` function is a no-op for this class
        like for any other python immutable type (eg: :class:`tuple`).
        """
        return dict(self)

    def __copy__(self):
        return self


class ImmutableMultiDict(ImmutableMultiDictMixin, MultiDict):
    """An immutable :class:`MultiDict`.
    """

    def copy(self):
        """Return a shallow mutable copy of this object.  Keep in mind that
        the standard library's :func:`copy` function is a no-op for this class
        like for any other python immutable type (eg: :class:`tuple`).
        """
        return MultiDict(self)

    def __copy__(self):
        return self


class ImmutableOrderedMultiDict(ImmutableMultiDictMixin, OrderedMultiDict):
    """An immutable :class:`OrderedMultiDict`.
    """

    def _iter_hashitems(self):
        return enumerate(self.items(multi=True))

    def copy(self):
        """Return a shallow mutable copy of this object.  Keep in mind that
        the standard library's :func:`copy` function is a no-op for this class
        like for any other python immutable type (eg: :class:`tuple`).
        """
        return OrderedMultiDict(self)

    def __copy__(self):
        return self


class CallbackDict(UpdateDictMixin, dict):
    """A dict that calls a function passed every time something is changed.
    The function is passed the dict instance.
    """

    def __init__(self, initial=None, on_update=None):
        dict.__init__(self, initial or ())
        self.on_update = on_update

    def __repr__(self):
        return '<%s %s>' % (
            self.__class__.__name__,
            dict.__repr__(self)
        )
