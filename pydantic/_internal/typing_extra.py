import sys
import types
from collections.abc import Callable
from os import PathLike
from typing import (  # type: ignore
    TYPE_CHECKING,
    AbstractSet,
    Any,
    Callable as TypingCallable,
    ClassVar,
    Dict,
    ForwardRef,
    Generator,
    Iterable,
    List,
    Mapping,
    NewType,
    NoReturn,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    _eval_type,
    cast,
    get_type_hints,
)

from pydantic_core.schema_types import Schema as PydanticCoreSchema
from typing_extensions import Annotated, Final, Literal, Required as TypedDictRequired

__all__ = (
    'AnyCallable',
    'NoArgAnyCallable',
    'NoneType',
    'is_none_type',
    'display_as_type',
    'resolve_annotations',
    'is_callable_type',
    'is_literal_type',
    'all_literal_values',
    'is_namedtuple',
    'is_typeddict',
    'is_typeddict_special',
    'is_new_type',
    'new_type_supertype',
    'is_classvar',
    'is_finalvar',
    'TupleGenerator',
    'DictStrAny',
    'DictAny',
    'SetStr',
    'ListStr',
    'IntStr',
    'AbstractSetIntStr',
    'DictIntStrAny',
    'CallableGenerator',
    'ReprArgs',
    'AnyClassMethod',
    'CallableGenerator',
    'WithArgsTypes',
    'get_args',
    'get_origin',
    'get_sub_types',
    'typing_base',
    'get_all_type_hints',
    'origin_is_union',
    'StrPath',
    'MappingIntStrAny',
    'NotRequired',
    'Required',
    'evaluate_forwardref',
    'FakeType',
    'ProtectAnnotated',
    'SchemaRef',
)

try:
    from typing import _TypingBase as typing_base  # type: ignore
except ImportError:
    from typing import _Final as typing_base  # type: ignore

try:
    from typing import GenericAlias as TypingGenericAlias  # type: ignore
except ImportError:
    # python < 3.9 does not have GenericAlias (list[int], tuple[str, ...] and so on)
    TypingGenericAlias = ()

try:
    from types import UnionType as TypesUnionType
except ImportError:
    # python < 3.10 does not have UnionType (str | int, byte | bool and so on)
    TypesUnionType = ()  # type: ignore[misc,assignment]


if sys.version_info < (3, 9):

    def evaluate_forwardref(type_: ForwardRef, globalns: Any, localns: Any = None) -> Any:
        return type_._evaluate(globalns, localns or None)

else:

    def evaluate_forwardref(type_: ForwardRef, globalns: Any, localns: Any = None) -> Any:
        # Even though it is the right signature for python 3.9, mypy complains with
        # `error: Too many arguments for "_evaluate" of "ForwardRef"` hence the cast...
        return cast(Any, type_)._evaluate(globalns, localns or None, set())


if sys.version_info < (3, 9):
    # Ensure we always get all the whole `Annotated` hint, not just the annotated type.
    # For 3.7 to 3.8, `get_type_hints` doesn't recognize `typing_extensions.Annotated`,
    # so it already returns the full annotation
    get_all_type_hints = get_type_hints

else:

    def get_all_type_hints(obj: Any, globalns: Any = None, localns: Any = None) -> Any:
        return get_type_hints(obj, globalns, localns, include_extras=True)


if sys.version_info < (3, 11):
    from typing_extensions import NotRequired, Required
else:
    from typing import NotRequired, Required

_T = TypeVar('_T')

AnyCallable = TypingCallable[..., Any]
NoArgAnyCallable = TypingCallable[[], Any]

# workaround for https://github.com/python/mypy/issues/9496
AnyArgTCallable = TypingCallable[..., _T]


# Annotated[...] is implemented by returning an instance of one of these classes, depending on
# python/typing_extensions version.
AnnotatedTypeNames = {'AnnotatedMeta', '_AnnotatedAlias'}


if sys.version_info < (3, 8):

    def get_origin(t: Type[Any]) -> Optional[Type[Any]]:
        if type(t).__name__ in AnnotatedTypeNames:
            # weirdly this is a runtime requirement, as well as for mypy
            return cast(Type[Any], Annotated)
        return getattr(t, '__origin__', None)

else:
    from typing import get_origin as _typing_get_origin

    def get_origin(tp: Type[Any]) -> Optional[Type[Any]]:
        """
        We can't directly use `typing.get_origin` since we need a fallback to support
        custom generic classes like `ConstrainedList`
        It should be useless once https://github.com/cython/cython/issues/3537 is
        solved and https://github.com/pydantic/pydantic/pull/1753 is merged.
        """
        if type(tp).__name__ in AnnotatedTypeNames:
            return cast(Type[Any], Annotated)  # mypy complains about _SpecialForm
        return _typing_get_origin(tp) or getattr(tp, '__origin__', None)


if sys.version_info < (3, 8):
    from typing import _GenericAlias

    def get_args(t: Type[Any]) -> Tuple[Any, ...]:
        """
        Compatibility version of get_args for python 3.7.

        Mostly compatible with the python 3.8 `typing` module version
        and able to handle almost all use cases.
        """
        if type(t).__name__ in AnnotatedTypeNames:
            return t.__args__ + t.__metadata__
        if isinstance(t, _GenericAlias):
            res = t.__args__
            if t.__origin__ is Callable and res and res[0] is not Ellipsis:
                res = (list(res[:-1]), res[-1])
            return res
        return getattr(t, '__args__', ())

else:
    from typing import get_args as _typing_get_args

    def _generic_get_args(tp: Type[Any]) -> Tuple[Any, ...]:
        """
        In python 3.9, `typing.Dict`, `typing.List`, ...
        do have an empty `__args__` by default (instead of the generic ~T for example).
        In order to still support `Dict` for example and consider it as `Dict[Any, Any]`,
        we retrieve the `_nparams` value that tells us how many parameters it needs.
        """
        if hasattr(tp, '_nparams'):
            return (Any,) * tp._nparams
        # Special case for `tuple[()]`, which used to return ((),) with `typing.Tuple`
        # in python 3.10- but now returns () for `tuple` and `Tuple`.
        # This will probably be clarified in pydantic v2
        try:
            if tp == Tuple[()] or sys.version_info >= (3, 9) and tp == tuple[()]:  # type: ignore[misc]
                return ((),)
        # there is a TypeError when compiled with cython
        except TypeError:  # pragma: no cover
            pass
        return ()

    def get_args(tp: Type[Any]) -> Tuple[Any, ...]:
        """
        Get type arguments with all substitutions performed.

        For unions, basic simplifications used by Union constructor are performed.
        Examples::
            get_args(Dict[str, int]) == (str, int)
            get_args(int) == ()
            get_args(Union[int, Union[T, int], str][int]) == (int, str)
            get_args(Union[int, Tuple[T, int]][str]) == (int, Tuple[str, int])
            get_args(Callable[[], T][int]) == ([], int)
        """
        if type(tp).__name__ in AnnotatedTypeNames:
            return tp.__args__ + tp.__metadata__
        # the fallback is needed for the same reasons as `get_origin` (see above)
        return _typing_get_args(tp) or getattr(tp, '__args__', ()) or _generic_get_args(tp)


if sys.version_info < (3, 9):

    def convert_generics(tp: Type[Any]) -> Type[Any]:
        """
        Python 3.9 and older only supports generics from `typing` module.
        They convert strings to ForwardRef automatically.

        Examples::
            typing.List['Hero'] == typing.List[ForwardRef('Hero')]
        """
        return tp

else:
    from typing import _UnionGenericAlias  # type: ignore

    from typing_extensions import _AnnotatedAlias

    def convert_generics(tp: Type[Any]) -> Type[Any]:
        """
        Recursively searches for `str` type hints and replaces them with ForwardRef.

        Examples::
            convert_generics(list['Hero']) == list[ForwardRef('Hero')]
            convert_generics(dict['Hero', 'Team']) == dict[ForwardRef('Hero'), ForwardRef('Team')]
            convert_generics(typing.Dict['Hero', 'Team']) == typing.Dict[ForwardRef('Hero'), ForwardRef('Team')]
            convert_generics(list[str | 'Hero'] | int) == list[str | ForwardRef('Hero')] | int
        """
        origin = get_origin(tp)
        if not origin or not hasattr(tp, '__args__'):
            return tp

        args = get_args(tp)

        # typing.Annotated needs special treatment
        if origin is Annotated:
            return _AnnotatedAlias(convert_generics(args[0]), args[1:])

        # recursively replace `str` instances inside of `GenericAlias` with `ForwardRef(arg)`
        converted = tuple(
            ForwardRef(arg) if isinstance(arg, str) and isinstance(tp, TypingGenericAlias) else convert_generics(arg)
            for arg in args
        )

        if converted == args:
            return tp
        elif isinstance(tp, TypingGenericAlias):
            return TypingGenericAlias(origin, converted)
        elif isinstance(tp, TypesUnionType):
            # recreate types.UnionType (PEP604, Python >= 3.10)
            return _UnionGenericAlias(origin, converted)
        else:
            try:
                setattr(tp, '__args__', converted)
            except AttributeError:
                pass
            return tp


if sys.version_info < (3, 10):

    def origin_is_union(tp: Optional[Type[Any]]) -> bool:
        return tp is Union

    WithArgsTypes = (TypingGenericAlias,)

else:
    import typing

    def origin_is_union(tp: Optional[Type[Any]]) -> bool:
        return tp is Union or tp is types.UnionType  # noqa: E721

    WithArgsTypes = (typing._GenericAlias, types.GenericAlias, types.UnionType)  # type: ignore[attr-defined]


if sys.version_info < (3, 9):
    StrPath = Union[str, PathLike]
else:
    StrPath = Union[str, PathLike]
    # TODO: Once we switch to Cython 3 to handle generics properly
    #  (https://github.com/cython/cython/issues/2753), use following lines instead
    #  of the one above
    # # os.PathLike only becomes subscriptable from Python 3.9 onwards
    # StrPath = Union[str, PathLike[str]]


if TYPE_CHECKING:
    TupleGenerator = Generator[Tuple[str, Any], None, None]
    DictStrAny = Dict[str, Any]
    DictAny = Dict[Any, Any]
    SetStr = Set[str]
    ListStr = List[str]
    IntStr = Union[int, str]
    AbstractSetIntStr = AbstractSet[IntStr]
    DictIntStrAny = Dict[IntStr, Any]
    MappingIntStrAny = Mapping[IntStr, Any]
    CallableGenerator = Generator[AnyCallable, None, None]
    ReprArgs = Iterable[Tuple[Optional[str], Any]]
    AnyClassMethod = classmethod[Any]


NoneType = None.__class__


NONE_TYPES: Tuple[Any, Any, Any] = (None, NoneType, Literal[None])


if sys.version_info < (3, 8):
    # Even though this implementation is slower, we need it for python 3.7:
    # In python 3.7 "Literal" is not a builtin type and uses a different
    # mechanism.
    # for this reason `Literal[None] is Literal[None]` evaluates to `False`,
    # breaking the faster implementation used for the other python versions.

    def is_none_type(type_: Any) -> bool:
        return type_ in NONE_TYPES

elif sys.version_info[:2] == (3, 8):

    def is_none_type(type_: Any) -> bool:
        for none_type in NONE_TYPES:
            if type_ is none_type:
                return True
        # With python 3.8, specifically 3.8.10, Literal "is" check sare very flakey
        # can change on very subtle changes like use of types in other modules,
        # hopefully this check avoids that issue.
        if is_literal_type(type_):  # pragma: no cover
            return all_literal_values(type_) == (None,)
        return False

else:

    def is_none_type(type_: Any) -> bool:
        for none_type in NONE_TYPES:
            if type_ is none_type:
                return True
        return False


def display_as_type(v: Type[Any]) -> str:
    """
    Pretty representation of a type, should be as close as possible to the original type definition string.

    TODO replace with typing._type_repr like logic.
    """
    if isinstance(v, types.FunctionType):
        return v.__name__

    if not isinstance(v, typing_base) and not isinstance(v, WithArgsTypes) and not isinstance(v, type):
        v = v.__class__

    if origin_is_union(get_origin(v)):
        return f'Union[{", ".join(map(display_as_type, get_args(v)))}]'

    if isinstance(v, WithArgsTypes):
        # Generic alias are constructs like `list[int]`
        return str(v).replace('typing.', '')

    try:
        return v.__name__
    except AttributeError:
        # happens with typing objects
        return str(v).replace('typing.', '')


def resolve_annotations(raw_annotations: Dict[str, Type[Any]], module_name: Optional[str]) -> Dict[str, Type[Any]]:
    """
    Partially taken from typing.get_type_hints.

    Resolve string or ForwardRef annotations into type objects if possible.
    """
    base_globals: Optional[Dict[str, Any]] = None
    if module_name:
        try:
            module = sys.modules[module_name]
        except KeyError:
            # happens occasionally, see https://github.com/pydantic/pydantic/issues/2363
            pass
        else:
            base_globals = module.__dict__

    annotations = {}
    for name, value in raw_annotations.items():
        if isinstance(value, str):
            if (3, 10) > sys.version_info >= (3, 9, 8) or sys.version_info >= (3, 10, 1):
                value = ForwardRef(value, is_argument=False, is_class=True)
            else:
                value = ForwardRef(value, is_argument=False)
        try:
            value = _eval_type(value, base_globals, None)
        except NameError:
            # this is ok, it can be fixed with update_forward_refs
            pass
        annotations[name] = value
    return annotations


def is_callable_type(type_: Type[Any]) -> bool:
    return type_ is Callable or get_origin(type_) is Callable


def is_literal_type(type_: Type[Any]) -> bool:
    return Literal is not None and get_origin(type_) is Literal


def literal_values(type_: Type[Any]) -> Tuple[Any, ...]:
    return get_args(type_)


def all_literal_values(type_: Type[Any]) -> Tuple[Any, ...]:
    """
    This method is used to retrieve all Literal values as
    Literal can be used recursively (see https://www.python.org/dev/peps/pep-0586)
    e.g. `Literal[Literal[Literal[1, 2, 3], "foo"], 5, None]`
    """
    if not is_literal_type(type_):
        return (type_,)

    values = literal_values(type_)
    return tuple(x for value in values for x in all_literal_values(value))


def is_namedtuple(type_: Type[Any]) -> bool:
    """
    Check if a given class is a named tuple.
    It can be either a `typing.NamedTuple` or `collections.namedtuple`
    """
    from ..utils import lenient_issubclass

    return lenient_issubclass(type_, tuple) and hasattr(type_, '_fields')


def is_typeddict(type_: Type[Any]) -> bool:
    """
    Check if a given class is a typed dict (from `typing` or `typing_extensions`)
    In 3.10, there will be a public method (https://docs.python.org/3.10/library/typing.html#typing.is_typeddict)
    """
    from ..utils import lenient_issubclass

    return lenient_issubclass(type_, dict) and hasattr(type_, '__total__')


def _check_typeddict_special(type_: Any) -> bool:
    return type_ is TypedDictRequired or type_ is NotRequired


def is_typeddict_special(type_: Any) -> bool:
    """
    Check if type is a TypedDict special form (Required or NotRequired).
    """
    return _check_typeddict_special(type_) or _check_typeddict_special(get_origin(type_))


test_type = NewType('test_type', str)


def is_new_type(type_: Type[Any]) -> bool:
    """
    Check whether type_ was created using typing.NewType
    """
    return isinstance(type_, test_type.__class__) and hasattr(type_, '__supertype__')  # type: ignore


def new_type_supertype(type_: Type[Any]) -> Type[Any]:
    while hasattr(type_, '__supertype__'):
        type_ = type_.__supertype__
    return type_


def _check_classvar(v: Optional[Type[Any]]) -> bool:
    if v is None:
        return False

    return v.__class__ == ClassVar.__class__ and getattr(v, '_name', None) == 'ClassVar'


def _check_finalvar(v: Optional[Type[Any]]) -> bool:
    """
    Check if a given type is a `typing.Final` type.
    """
    if v is None:
        return False

    return v.__class__ == Final.__class__ and (sys.version_info < (3, 8) or getattr(v, '_name', None) == 'Final')


def is_classvar(ann_type: Type[Any]) -> bool:
    if _check_classvar(ann_type) or _check_classvar(get_origin(ann_type)):
        return True

    # this is an ugly workaround for class vars that contain forward references and are therefore themselves
    # forward references, see #3679
    if ann_type.__class__ == ForwardRef and ann_type.__forward_arg__.startswith('ClassVar['):
        return True

    return False


def is_finalvar(ann_type: Type[Any]) -> bool:
    return _check_finalvar(ann_type) or _check_finalvar(get_origin(ann_type))


def get_class(type_: Type[Any]) -> Union[None, bool, Type[Any]]:
    """
    Tries to get the class of a Type[T] annotation. Returns True if Type is used
    without brackets. Otherwise returns None.
    """
    if type_ is type:
        return True

    if get_origin(type_) is None:
        return None

    args = get_args(type_)
    if not args or not isinstance(args[0], type):
        return True
    else:
        return args[0]


def get_sub_types(tp: Any) -> List[Any]:
    """
    Return all the types that are allowed by type `tp`
    `tp` can be a `Union` of allowed types or an `Annotated` type
    """
    origin = get_origin(tp)
    if origin is Annotated:
        return get_sub_types(get_args(tp)[0])
    elif origin_is_union(origin):
        return [x for t in get_args(tp) for x in get_sub_types(t)]
    else:
        return [tp]


class FakeType:
    """
    Just enough like a "typing type" to mollify `typing._type_check`.
    """

    def __call__(self) -> NoReturn:
        """
        This is here just to mollify typing._type_check which expects "typing types"
        but will also accept callables
        """
        raise TypeError(f'{self} cannot be called')

    def __or__(self, right: Any) -> Any:
        return Union[self, right]

    def __ror__(self, left: Any) -> Any:
        return Union[left, self]


class ProtectAnnotated(FakeType):
    """
    This is a hack to allow `Annotated` info to pass through `get_type_hints` without being stripped out
    in 3.7 and 3.8 which don't support the `include_extras` argument to `get_type_hints`.
    """

    __slots__ = ('annotated_type',)

    def __init__(self, annotated_type: Any):
        self.annotated_type = annotated_type

    def __repr__(self) -> str:
        return f'ProtectAnnotated[{self.annotated_type}]'


class SchemaRef(FakeType):
    """
    Pretend to be a type for `get_type_hints` while holding schema info.
    """

    __slots__ = '_name', '__pydantic_validation_schema__'

    def __init__(self, name: str, core_schema: PydanticCoreSchema):
        self._name = name
        self.__pydantic_validation_schema__ = core_schema

    def __repr__(self) -> str:
        return f'SchemaRef({self._name!r}, {self.__pydantic_validation_schema__})'
