#! /usr/bin/env python

from __future__ import print_function, division, absolute_import
from fontTools.misc.py23 import *

import sympy as sp
import sys
from fontTools.pens.basePen import BasePen
from functools import partial
from itertools import count

n = 3 # Max Bezier degree; 3 for cubic, 2 for quadratic

t, x, y = sp.symbols('t x y', real=True)
c = sp.symbols('c', real=False) # Complex representation instead of x/y

X = tuple(sp.symbols('x:%d'%(n+1), real=True))
Y = tuple(sp.symbols('y:%d'%(n+1), real=True))
P = tuple(zip(*(sp.symbols('p:%d[%s]'%(n+1,w), real=True) for w in '01')))
C = tuple(sp.symbols('c:%d'%(n+1), real=False))

# Cubic Bernstein basis functions
BinomialCoefficient = [(1, 0)]
for i in range(1, n+1):
	last = BinomialCoefficient[-1]
	this = tuple(last[j-1]+last[j] for j in range(len(last)))+(0,)
	BinomialCoefficient.append(this)
BinomialCoefficient = tuple(tuple(item[:-1]) for item in BinomialCoefficient)
del last, this

BernsteinPolynomial = tuple(
	tuple(c * t**i * (1-t)**(n-i) for i,c in enumerate(coeffs))
	for n,coeffs in enumerate(BinomialCoefficient))

BezierCurve = tuple(
	tuple(sum(P[i][j]*bernstein for i,bernstein in enumerate(bernsteins))
		for j in range(2))
	for n,bernsteins in enumerate(BernsteinPolynomial))
BezierCurveC = tuple(
	sum(C[i]*bernstein for i,bernstein in enumerate(bernsteins))
	for n,bernsteins in enumerate(BernsteinPolynomial))

def green(f, curveXY):
	f = -sp.integrate(sp.sympify(f), y)
	f = f.subs({x:curveXY[0], y:curveXY[1]})
	f = sp.integrate(f * sp.diff(curveXY[0], t), (t, 0, 1))
	return f

def printPen(penName, funcs, file=sys.stdout):
	print(
'''from __future__ import print_function, division, absolute_import
from fontTools.misc.py23 import *
from fontTools.pens.basePen import BasePen

class %s(BasePen):

	def __init__(self, glyphset=None):
		BasePen.__init__(self, glyphset)
'''%penName, file=file)
	for name,f in funcs:
		print('		self.%s = 0' % name, file=file)
	print('''
	def _moveTo(self, p0):
		self.__startPoint = p0

	def _closePath(self):
		p0 = self._getCurrentPoint()
		if p0 != self.__startPoint:
			self._lineTo(self.__startPoint)

	def _endPath(self):
		p0 = self._getCurrentPoint()
		if p0 != self.__startPoint:
			# Green theorem is not defined on open contours.
			raise NotImplementedError
''', end='', file=file)

	for n in (1, 2, 3):

		if n == 1:
			print('''
	def _lineTo(self, p1):
		x0,y0 = self._getCurrentPoint()
		x1,y1 = p1
''', file=file)
		elif n == 2:
			print('''
	def _qCurveToOne(self, p1, p2):
		x0,y0 = self._getCurrentPoint()
		x1,y1 = p1
		x2,y2 = p2
''', file=file)
		elif n == 3:
			print('''
	def _curveToOne(self, p1, p2, p3):
		x0,y0 = self._getCurrentPoint()
		x1,y1 = p1
		x2,y2 = p2
		x3,y3 = p3
''', file=file)
		subs = {P[i][j]: [X, Y][j][i] for i in range(n+1) for j in range(2)}
		greens = [green(f, BezierCurve[n]) for name,f in funcs]
		greens = [sp.gcd_terms(f.collect(sum(P,()))) for f in greens] # Optimize
		greens = [f.subs(subs) for f in greens] # Convert to p to x/y
		defs, exprs = sp.cse(greens,
				     optimizations='basic',
				     symbols=(sp.Symbol('r%d'%i) for i in count()))
		for name,value in defs:
			print('		%s = %s' % (name, value), file=file)
		print(file=file)
		for name,value in zip([f[0] for f in funcs], exprs):
			print('		self.%s += %s' % (name, value), file=file)

	print('''
if __name__ == '__main__':
	from symfont import x, y, printPen
	printPen('%s', ['''%penName, file=file)
	for name,f in funcs:
		print("		 ('%s', %s)," % (name, str(f)), file=file)
	print('		])', file=file)


class BezierFuncs(dict):

	def __init__(self, symfunc):
		self._symfunc = symfunc
		self._bezfuncs = {}

	def __missing__(self, i):
		args = ['p%d'%d for d in range(i+1)]
		f = green(self._symfunc, BezierCurve[i])
		f = sp.gcd_terms(f.collect(sum(P,()))) # Optimize
		return sp.lambdify(args, f)

class GreenPen(BasePen):

	_BezierFuncs = {}

	@classmethod
	def _getGreenBezierFuncs(celf, func):
		funcstr = str(func)
		if not funcstr in celf._BezierFuncs:
			celf._BezierFuncs[funcstr] = BezierFuncs(func)
		return celf._BezierFuncs[funcstr]

	def __init__(self, func, glyphset=None):
		BasePen.__init__(self, glyphset)
		self._funcs = self._getGreenBezierFuncs(func)
		self.value = 0

	def _moveTo(self, p0):
		self.__startPoint = p0

	def _closePath(self):
		p0 = self._getCurrentPoint()
		if p0 != self.__startPoint:
			self._lineTo(self.__startPoint)

	def _endPath(self):
		p0 = self._getCurrentPoint()
		if p0 != self.__startPoint:
			# Green theorem is not defined on open contours.
			raise NotImplementedError

	def _lineTo(self, p1):
		p0 = self._getCurrentPoint()
		self.value += self._funcs[1](p0, p1)

	def _qCurveToOne(self, p1, p2):
		p0 = self._getCurrentPoint()
		self.value += self._funcs[2](p0, p1, p2)

	def _curveToOne(self, p1, p2, p3):
		p0 = self._getCurrentPoint()
		self.value += self._funcs[3](p0, p1, p2, p3)

# Sample pens.
# Do not use this in real code.
# Use fontTools.pens.momentsPen.MomentsPen instead.
AreaPen = partial(GreenPen, func=1)
MomentXPen = partial(GreenPen, func=x)
MomentYPen = partial(GreenPen, func=y)
MomentXXPen = partial(GreenPen, func=x*x)
MomentYYPen = partial(GreenPen, func=y*y)
MomentXYPen = partial(GreenPen, func=x*y)


if __name__ == '__main__':
	pen = AreaPen()
	pen.moveTo((100,100))
	pen.lineTo((100,200))
	pen.lineTo((200,200))
	pen.curveTo((200,250),(300,300),(250,350))
	pen.lineTo((200,100))
	pen.closePath()
	print(pen.value)
