"""testing various type hint features and syntaxes"""
from typing import Generic, TypeVarTuple, Union, Unpack, TypeVar
# from typing_extensions import reveal_type


def test():
    """old syntax"""
    class A[T]:
        a: T

    def f[T](*args:T) -> type[A[Union[T]]]:
        ...

    a = f(1,'a', True, 4.5)()
    a.a

def test():
    """new syntax"""
    T = TypeVar('T')
    class A(Generic[T]):
        a: T

    def f(*args:T) -> type[A[Union[T]]]:
        ...

    a = f(1,'a', True, 4.5)()
    a.a


from typing import Generic, TypeVarTuple, Union, Unpack, TypeVar


def test_either():
    """old syntax"""
    T = TypeVar('T')

    class Either(Generic[T]):
        a: T
    def either(*args:Union[type[T]]) -> type[Either[Union[T]]]: ...
    class A: ...
    class B: ...

    rule = either(A, B)
    rule('a').a


def test_either():
    """new syntax"""
    class Either[T]:
        a: T
    def either[T](*args:Union[type[T]]) -> type[Either[Union[T]]]: ...
    class A: ...
    class B: ...
    
    rule = either(A, B)
    rule('a').a



def test_repeat():
    """old syntax"""
    class Infinity: ...
    infinity = Infinity()

    T = TypeVar('T')
    class Repeat(Generic[T]):
        items: list[T]
    def repeat(arg:type[T], /, *, separator:str='', at_least:int=0, at_most:int|Infinity=infinity, exactly:int=None) -> type[Repeat[T]]: ...
    class A: ...

    rule = repeat(A)
    rule('aaaa').items


def test_repeat():
    """new syntax"""
    class Repeat[T]:
        items: list[T]
    def repeat[T](arg:type[T]) -> type[Repeat[T]]: ...
    class A: ...

    rule = repeat(A)
    rule('aaaa').items



def test_optional():
    """old syntax"""
    T = TypeVar('T')
    class Optional(Generic[T]):
        item: T|None
    def optional(arg:type[T]) -> type[Optional[T]]: ...
    class A: ...
    rule = optional(A)
    rule('a').item

def test_optional():
    """new syntax"""
    class Optional[T]:
        item: T|None
    def optional[T](arg:type[T]) -> type[Optional[T]]: ...
    class A: ...
    rule = optional(A)
    rule('a').item


def test_sequence():
    """old syntax"""
    Ts = TypeVarTuple('Ts')
    class Sequence(Generic[Unpack[Ts]]):
        items: tuple[Unpack[Ts]]
    class A: ...
    class B: ...

    rule = Sequence[A, B, B, A]
    rule('abba').items
    
    # not quite right. gives items: tuple[type[A], type[B], type[B], type[A]], not tuple[A, B, B, A]
    def sequence(*args:Unpack[Ts]) -> type[Sequence[Unpack[Ts]]]: ...
    rule1 = sequence(A, B, B, A)
    rule1('abba').items

def test_sequence():
    """new syntax"""
    class Sequence[*Ts]:
        items: tuple[*Ts]
    class A: ...
    class B: ...

    rule = Sequence[A, B, B, A]
    rule('abba').items

    def sequence[*Ts](*args:*Ts) -> type[Sequence[*Ts]]: ...
    rule1 = sequence(A, B, B, A)
    rule1('abba').items


def test_sequence_hack():
    """new syntax, hacky"""
    from typing import overload, Any
    class Sequence[*Ts]:
        items: tuple[*Ts]
    
    @overload
    def sequence[A](a:type[A]) -> type[Sequence[A]]: ...
    @overload
    def sequence[A, B](a:type[A], b:type[B]) -> type[Sequence[A, B]]: ...
    @overload
    def sequence[A, B, C](a:type[A], b:type[B], c:type[C]) -> type[Sequence[A, B, C]]: ...
    @overload
    def sequence[A, B, C, D](a:type[A], b:type[B], c:type[C], d:type[D]) -> type[Sequence[A, B, C, D]]: ...
    # @overload
    # def sequence[A, B, C, D, E](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E]) -> type[Sequence[A, B, C, D, E]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F]) -> type[Sequence[A, B, C, D, E, F]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G]) -> type[Sequence[A, B, C, D, E, F, G]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H]) -> type[Sequence[A, B, C, D, E, F, G, H]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I]) -> type[Sequence[A, B, C, D, E, F, G, H, I]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L, M](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[S]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[T]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L,
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[T], u:type[U]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[T], u:type[U], v:type[V]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[T], u:type[U], v:type[V], w:type[W]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[T], u:type[U], v:type[V], w:type[W], x:type[X]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X, Y](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[T], u:type[U], v:type[V], w:type[W], x:type[X], y:type[Y]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X, Y]]: ...
    # @overload
    # def sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X, Y, Z](a:type[A], b:type[B], c:type[C], d:type[D], e:type[E], f:type[F], g:type[G], h:type[H], i:type[I], j:type[J], k:type[K], l:type[L], m:type[M], n:type[N], o:type[O], p:type[P], q:type[Q], r:type[R], s:type[T], u:type[U], v:type[V], w:type[W], x:type[X], y:type[Y], z:type[Z]) -> type[Sequence[A, B, C, D, E, F, G, H, I, J, K, L, M, N, O, P, Q, R, S, T, U, V, W, X, Y, Z]]: ...
    
    # give up and just say it's a tuple of unions of all the possible args
    @overload
    def sequence[T](*args:type[T]) -> type[Sequence[Union[T], ...]]: ...
    def sequence[T](*args:T) -> type[Sequence[Union[T], ...]]: ...
    class A: ...
    class B: ...

    sequence

    rule = sequence(B, A, B, B, B, B, B, B, A, A, A)
    rule('abba').items

# a = A[int, str]()
# b = a.a