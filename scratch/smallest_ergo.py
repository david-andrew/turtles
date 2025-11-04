# basically a minimal scheme/lisp style parser


"""
Token types:
- parenthesis
- delimited strings
- reserved words (potentially just assigned delimited strings...)
- non-delimited strings/identifiers (i.e. everything else)

- tbd about other atom token types. proabably also have integer


syntax goals:
- fn declaration
    (fn (<args>) (<expression>))
    (fn (x y) (+ x y))
- variable assignment
    (= name value)
    (= x 10)
    (= add5 (fn x (+ x 5)))
    (= mylist (1 2 3 4 5))
    (= mystr 'something')

(maybe)
- simple partial eval. could basically treat all functions like functional curried functions. so can apply values in the declaration sequence (but can't go out of order)
    (= add (fn (x y) (+ x y)))
    (= add5 (add 5))
- variable arg functions?
    (+ 1 2 3 4 5)
    probably need special syntax to handle it, e.g.
    (= fn= (fn (name ... expr) (= [name] (fn (...) expr))))  // seems like a pain in the butt lol



[functions to add]
- string interpolator
(= apple 1)
(= banana 2)
(= peach 3)
(= pear 4)
(= pineapple 5)
(join 'a ' apple ' string ' banana ' with ' 42 ' lots ' peach ' of ' pear ' interpolated ' pineapple ' values ' (+ 1 2 3 4 5))
// 'a 1 string 2 with 42 lots 3 of 4 interpolated 5 values 15'


[examples]
(= prompt (fn (msg) (do (print msg) readl)))
(do
  (= name (prompt "what's your name? "))
  (printl (join 'Hello ' name '!')))



Chatgpt mentioned I probably want a way to quote a list in a `do` block. I think perhaps we can just have an express keyword which does this
```
(do
    (express (1 2 3 4 5 6))
)
```
apparently this is commonly accomplished with quoting?
```
(do '(1 2 3 4 5 6))
```
"""

# want tokenizing/parsing to be more combined
# also should be generators. i.e. tokenize()->Generator[Token], parse()->Generator[Expr]

from typing import Generator
from dataclasses import dataclass

import pdb

@dataclass
class Id:
    value: str

@dataclass
class LeftParen: ...
@dataclass
class RightParen: ...
left_paren = LeftParen()
right_paren = RightParen()

ESCAPE_MAP = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "\\": "\\",
    '"': '"',
    "'": "'",
    "0": "\0",
}

whitespace = ' \r\n\t'

type Token = int|str|Id|LeftParen|RightParen
def tokenize(src:str) -> Generator[Token]:
    while len(src) > 0:
        # whitespace and comments
        if src[0] in whitespace:
            src = src[1:]
            continue

        # line comment
        if src.startswith('//'):
            i = 2
            while i < len(src) and src[i] != '\n': i+=1
            src = src[i:]
            continue

        # block comment (allowing nested comments)
        if src.startswith('/*'):
            stack = 1
            i = 2
            while i < len(src) and stack > 0:
                if src.startswith('/*'):
                    i += 2
                    stack += 1
                elif src.startswith('*/'):
                    i += 2
                    stack -= 1
                else:
                    i += 1
            if stack != 0:
                raise ValueError(f'Unclosed block comment. remaining=`{src}`')
            src = src[i:]
            continue

        # left/right parenthesis
        if src[0] == '(':
            src = src[1:]
            yield left_paren
            continue
        if src[0] == ')':
            src = src[1:]
            yield right_paren
            continue

        # integers
        if src[0].isnumeric():
            i = 1
            while i < len(src) and src[i].isnumeric(): i+=1
            yield int(src[:i])
            src = src[i:]
            continue

        # strings
        if src[0] == '"' or src[0] == "'":
            delim = src[0]
            s = ''
            i = 1
            while i < len(src):
                if src[i] == delim:
                    i += 1
                    break
                if src[i] == '\\':
                    i += 1
                    if not i < len(src):
                        raise ValueError(f'Unclosed string literal. remaining=`{src}`')
                    # just insert the literal character escaped if not recognized
                    s += ESCAPE_MAP[src[i]] if src[i] in ESCAPE_MAP else src[i]
                else:
                    s += src[i]
                i += 1
            if src[i-1] != delim:
                raise ValueError(f"Unclosed string literal. remaining=`{src}`")
            yield s
            src = src[i:]
            continue

        # everything else is recognized as an identifier
        # because we're lazy about delimiting identifiers, they can contain comments and strings
        i = 0
        while i < len(src) and src[i] not in whitespace and src[i] not in '()':
            i += 1
        yield Id(src[:i])
        src = src[i:]


# in general, shouldn't actually pre-parse. just evaluate immediately...
type Expr = list[Expr]|Id|str|int
def parse(tokens:Generator[Token]) -> Generator[Expr]:
    stack = []

    # for t in tokens:
    while True:
        try:
            t = next(tokens)
        except StopIteration:
            if len(stack) > 0:
                raise ValueError(f'Unclosed list encounted. Current expression stack: {stack=}')
            break
        if isinstance(t, LeftParen):
            stack.append([])
            continue
        if isinstance(t, (Id, str, int)):
            if len(stack) == 0:
                raise ValueError(f'Encountered atom tokens without enclosing list. {t=}')
            stack[-1].append(t)
            continue
        if isinstance(t, RightParen):
            if len(stack) == 0:
                raise ValueError(f'Encountered closing paren with no matching opening. {t=}')
            l = stack.pop()
            if len(stack) == 0:
                yield l
            else:
                stack[-1].append(l)
            continue



class Runtime:
    def __init__(self):
        self.vars = {}
    # def assign(self, name:str, value:int|str|list):
    #     self.vars[name] = value

    # def get(self, name:str):
    #     return self.vars[name]

    def eval(self, s:str):
        tokens = tokenize(s)
        exprs = parse(tokens)
        for expr in exprs:
            # TODO: eval the expr
            print(expr)
        pdb.set_trace()




if __name__ == '__main__':
    rt = Runtime()
    rt.eval('(print "Hello, World!\n")')


    from easyrepl import REPL
    for query in REPL(history_file='.chat'):
        print(' '.join(map(str, parse(tokenize(query)))))
