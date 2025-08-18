/**
* @vue/shared v3.5.13
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
/*! #__NO_SIDE_EFFECTS__ */
// @__NO_SIDE_EFFECTS__
function bs(e) {
  const t = /* @__PURE__ */ Object.create(null);
  for (const s of e.split(",")) t[s] = 1;
  return (s) => s in t;
}
const U = {}, Ye = [], ye = () => {
}, Ei = () => !1, Lt = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // uppercase letter
(e.charCodeAt(2) > 122 || e.charCodeAt(2) < 97), ys = (e) => e.startsWith("onUpdate:"), te = Object.assign, xs = (e, t) => {
  const s = e.indexOf(t);
  s > -1 && e.splice(s, 1);
}, Ti = Object.prototype.hasOwnProperty, D = (e, t) => Ti.call(e, t), P = Array.isArray, ze = (e) => Vt(e) === "[object Map]", mn = (e) => Vt(e) === "[object Set]", R = (e) => typeof e == "function", G = (e) => typeof e == "string", Fe = (e) => typeof e == "symbol", J = (e) => e !== null && typeof e == "object", bn = (e) => (J(e) || R(e)) && R(e.then) && R(e.catch), yn = Object.prototype.toString, Vt = (e) => yn.call(e), Ci = (e) => Vt(e).slice(8, -1), xn = (e) => Vt(e) === "[object Object]", vs = (e) => G(e) && e !== "NaN" && e[0] !== "-" && "" + parseInt(e, 10) === e, lt = /* @__PURE__ */ bs(
  // the leading comma is intentional so empty string "" is also included
  ",key,ref,ref_for,ref_key,onVnodeBeforeMount,onVnodeMounted,onVnodeBeforeUpdate,onVnodeUpdated,onVnodeBeforeUnmount,onVnodeUnmounted"
), Ut = (e) => {
  const t = /* @__PURE__ */ Object.create(null);
  return (s) => t[s] || (t[s] = e(s));
}, Oi = /-(\w)/g, Me = Ut(
  (e) => e.replace(Oi, (t, s) => s ? s.toUpperCase() : "")
), Ai = /\B([A-Z])/g, Je = Ut(
  (e) => e.replace(Ai, "-$1").toLowerCase()
), vn = Ut((e) => e.charAt(0).toUpperCase() + e.slice(1)), zt = Ut(
  (e) => e ? `on${vn(e)}` : ""
), Be = (e, t) => !Object.is(e, t), Xt = (e, ...t) => {
  for (let s = 0; s < e.length; s++)
    e[s](...t);
}, Sn = (e, t, s, n = !1) => {
  Object.defineProperty(e, t, {
    configurable: !0,
    enumerable: !1,
    writable: n,
    value: s
  });
}, Pi = (e) => {
  const t = parseFloat(e);
  return isNaN(t) ? e : t;
};
let Ks;
const Bt = () => Ks || (Ks = typeof globalThis < "u" ? globalThis : typeof self < "u" ? self : typeof window < "u" ? window : typeof global < "u" ? global : {});
function Ss(e) {
  if (P(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++) {
      const n = e[s], i = G(n) ? Fi(n) : Ss(n);
      if (i)
        for (const r in i)
          t[r] = i[r];
    }
    return t;
  } else if (G(e) || J(e))
    return e;
}
const Ri = /;(?![^(]*\))/g, Ii = /:([^]+)/, Mi = /\/\*[^]*?\*\//g;
function Fi(e) {
  const t = {};
  return e.replace(Mi, "").split(Ri).forEach((s) => {
    if (s) {
      const n = s.split(Ii);
      n.length > 1 && (t[n[0].trim()] = n[1].trim());
    }
  }), t;
}
function ws(e) {
  let t = "";
  if (G(e))
    t = e;
  else if (P(e))
    for (let s = 0; s < e.length; s++) {
      const n = ws(e[s]);
      n && (t += n + " ");
    }
  else if (J(e))
    for (const s in e)
      e[s] && (t += s + " ");
  return t.trim();
}
const Di = "itemscope,allowfullscreen,formnovalidate,ismap,nomodule,novalidate,readonly", ji = /* @__PURE__ */ bs(Di);
function wn(e) {
  return !!e || e === "";
}
const En = (e) => !!(e && e.__v_isRef === !0), Tn = (e) => G(e) ? e : e == null ? "" : P(e) || J(e) && (e.toString === yn || !R(e.toString)) ? En(e) ? Tn(e.value) : JSON.stringify(e, Cn, 2) : String(e), Cn = (e, t) => En(t) ? Cn(e, t.value) : ze(t) ? {
  [`Map(${t.size})`]: [...t.entries()].reduce(
    (s, [n, i], r) => (s[Zt(n, r) + " =>"] = i, s),
    {}
  )
} : mn(t) ? {
  [`Set(${t.size})`]: [...t.values()].map((s) => Zt(s))
} : Fe(t) ? Zt(t) : J(t) && !P(t) && !xn(t) ? String(t) : t, Zt = (e, t = "") => {
  var s;
  return (
    // Symbol.description in es2019+ so we need to cast here to pass
    // the lib: es2016 check
    Fe(e) ? `Symbol(${(s = e.description) != null ? s : t})` : e
  );
};
/**
* @vue/reactivity v3.5.13
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let oe;
class $i {
  constructor(t = !1) {
    this.detached = t, this._active = !0, this.effects = [], this.cleanups = [], this._isPaused = !1, this.parent = oe, !t && oe && (this.index = (oe.scopes || (oe.scopes = [])).push(
      this
    ) - 1);
  }
  get active() {
    return this._active;
  }
  pause() {
    if (this._active) {
      this._isPaused = !0;
      let t, s;
      if (this.scopes)
        for (t = 0, s = this.scopes.length; t < s; t++)
          this.scopes[t].pause();
      for (t = 0, s = this.effects.length; t < s; t++)
        this.effects[t].pause();
    }
  }
  /**
   * Resumes the effect scope, including all child scopes and effects.
   */
  resume() {
    if (this._active && this._isPaused) {
      this._isPaused = !1;
      let t, s;
      if (this.scopes)
        for (t = 0, s = this.scopes.length; t < s; t++)
          this.scopes[t].resume();
      for (t = 0, s = this.effects.length; t < s; t++)
        this.effects[t].resume();
    }
  }
  run(t) {
    if (this._active) {
      const s = oe;
      try {
        return oe = this, t();
      } finally {
        oe = s;
      }
    }
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  on() {
    oe = this;
  }
  /**
   * This should only be called on non-detached scopes
   * @internal
   */
  off() {
    oe = this.parent;
  }
  stop(t) {
    if (this._active) {
      this._active = !1;
      let s, n;
      for (s = 0, n = this.effects.length; s < n; s++)
        this.effects[s].stop();
      for (this.effects.length = 0, s = 0, n = this.cleanups.length; s < n; s++)
        this.cleanups[s]();
      if (this.cleanups.length = 0, this.scopes) {
        for (s = 0, n = this.scopes.length; s < n; s++)
          this.scopes[s].stop(!0);
        this.scopes.length = 0;
      }
      if (!this.detached && this.parent && !t) {
        const i = this.parent.scopes.pop();
        i && i !== this && (this.parent.scopes[this.index] = i, i.index = this.index);
      }
      this.parent = void 0;
    }
  }
}
function Hi() {
  return oe;
}
let V;
const Qt = /* @__PURE__ */ new WeakSet();
class On {
  constructor(t) {
    this.fn = t, this.deps = void 0, this.depsTail = void 0, this.flags = 5, this.next = void 0, this.cleanup = void 0, this.scheduler = void 0, oe && oe.active && oe.effects.push(this);
  }
  pause() {
    this.flags |= 64;
  }
  resume() {
    this.flags & 64 && (this.flags &= -65, Qt.has(this) && (Qt.delete(this), this.trigger()));
  }
  /**
   * @internal
   */
  notify() {
    this.flags & 2 && !(this.flags & 32) || this.flags & 8 || Pn(this);
  }
  run() {
    if (!(this.flags & 1))
      return this.fn();
    this.flags |= 2, Ws(this), Rn(this);
    const t = V, s = ce;
    V = this, ce = !0;
    try {
      return this.fn();
    } finally {
      In(this), V = t, ce = s, this.flags &= -3;
    }
  }
  stop() {
    if (this.flags & 1) {
      for (let t = this.deps; t; t = t.nextDep)
        Cs(t);
      this.deps = this.depsTail = void 0, Ws(this), this.onStop && this.onStop(), this.flags &= -2;
    }
  }
  trigger() {
    this.flags & 64 ? Qt.add(this) : this.scheduler ? this.scheduler() : this.runIfDirty();
  }
  /**
   * @internal
   */
  runIfDirty() {
    ls(this) && this.run();
  }
  get dirty() {
    return ls(this);
  }
}
let An = 0, ft, ct;
function Pn(e, t = !1) {
  if (e.flags |= 8, t) {
    e.next = ct, ct = e;
    return;
  }
  e.next = ft, ft = e;
}
function Es() {
  An++;
}
function Ts() {
  if (--An > 0)
    return;
  if (ct) {
    let t = ct;
    for (ct = void 0; t; ) {
      const s = t.next;
      t.next = void 0, t.flags &= -9, t = s;
    }
  }
  let e;
  for (; ft; ) {
    let t = ft;
    for (ft = void 0; t; ) {
      const s = t.next;
      if (t.next = void 0, t.flags &= -9, t.flags & 1)
        try {
          t.trigger();
        } catch (n) {
          e || (e = n);
        }
      t = s;
    }
  }
  if (e) throw e;
}
function Rn(e) {
  for (let t = e.deps; t; t = t.nextDep)
    t.version = -1, t.prevActiveLink = t.dep.activeLink, t.dep.activeLink = t;
}
function In(e) {
  let t, s = e.depsTail, n = s;
  for (; n; ) {
    const i = n.prevDep;
    n.version === -1 ? (n === s && (s = i), Cs(n), Ni(n)) : t = n, n.dep.activeLink = n.prevActiveLink, n.prevActiveLink = void 0, n = i;
  }
  e.deps = t, e.depsTail = s;
}
function ls(e) {
  for (let t = e.deps; t; t = t.nextDep)
    if (t.dep.version !== t.version || t.dep.computed && (Mn(t.dep.computed) || t.dep.version !== t.version))
      return !0;
  return !!e._dirty;
}
function Mn(e) {
  if (e.flags & 4 && !(e.flags & 16) || (e.flags &= -17, e.globalVersion === pt))
    return;
  e.globalVersion = pt;
  const t = e.dep;
  if (e.flags |= 2, t.version > 0 && !e.isSSR && e.deps && !ls(e)) {
    e.flags &= -3;
    return;
  }
  const s = V, n = ce;
  V = e, ce = !0;
  try {
    Rn(e);
    const i = e.fn(e._value);
    (t.version === 0 || Be(i, e._value)) && (e._value = i, t.version++);
  } catch (i) {
    throw t.version++, i;
  } finally {
    V = s, ce = n, In(e), e.flags &= -3;
  }
}
function Cs(e, t = !1) {
  const { dep: s, prevSub: n, nextSub: i } = e;
  if (n && (n.nextSub = i, e.prevSub = void 0), i && (i.prevSub = n, e.nextSub = void 0), s.subs === e && (s.subs = n, !n && s.computed)) {
    s.computed.flags &= -5;
    for (let r = s.computed.deps; r; r = r.nextDep)
      Cs(r, !0);
  }
  !t && !--s.sc && s.map && s.map.delete(s.key);
}
function Ni(e) {
  const { prevDep: t, nextDep: s } = e;
  t && (t.nextDep = s, e.prevDep = void 0), s && (s.prevDep = t, e.nextDep = void 0);
}
let ce = !0;
const Fn = [];
function De() {
  Fn.push(ce), ce = !1;
}
function je() {
  const e = Fn.pop();
  ce = e === void 0 ? !0 : e;
}
function Ws(e) {
  const { cleanup: t } = e;
  if (e.cleanup = void 0, t) {
    const s = V;
    V = void 0;
    try {
      t();
    } finally {
      V = s;
    }
  }
}
let pt = 0;
class Li {
  constructor(t, s) {
    this.sub = t, this.dep = s, this.version = s.version, this.nextDep = this.prevDep = this.nextSub = this.prevSub = this.prevActiveLink = void 0;
  }
}
class Dn {
  constructor(t) {
    this.computed = t, this.version = 0, this.activeLink = void 0, this.subs = void 0, this.map = void 0, this.key = void 0, this.sc = 0;
  }
  track(t) {
    if (!V || !ce || V === this.computed)
      return;
    let s = this.activeLink;
    if (s === void 0 || s.sub !== V)
      s = this.activeLink = new Li(V, this), V.deps ? (s.prevDep = V.depsTail, V.depsTail.nextDep = s, V.depsTail = s) : V.deps = V.depsTail = s, jn(s);
    else if (s.version === -1 && (s.version = this.version, s.nextDep)) {
      const n = s.nextDep;
      n.prevDep = s.prevDep, s.prevDep && (s.prevDep.nextDep = n), s.prevDep = V.depsTail, s.nextDep = void 0, V.depsTail.nextDep = s, V.depsTail = s, V.deps === s && (V.deps = n);
    }
    return s;
  }
  trigger(t) {
    this.version++, pt++, this.notify(t);
  }
  notify(t) {
    Es();
    try {
      for (let s = this.subs; s; s = s.prevSub)
        s.sub.notify() && s.sub.dep.notify();
    } finally {
      Ts();
    }
  }
}
function jn(e) {
  if (e.dep.sc++, e.sub.flags & 4) {
    const t = e.dep.computed;
    if (t && !e.dep.subs) {
      t.flags |= 20;
      for (let n = t.deps; n; n = n.nextDep)
        jn(n);
    }
    const s = e.dep.subs;
    s !== e && (e.prevSub = s, s && (s.nextSub = e)), e.dep.subs = e;
  }
}
const fs = /* @__PURE__ */ new WeakMap(), Ke = Symbol(
  ""
), cs = Symbol(
  ""
), gt = Symbol(
  ""
);
function z(e, t, s) {
  if (ce && V) {
    let n = fs.get(e);
    n || fs.set(e, n = /* @__PURE__ */ new Map());
    let i = n.get(s);
    i || (n.set(s, i = new Dn()), i.map = n, i.key = s), i.track();
  }
}
function Te(e, t, s, n, i, r) {
  const o = fs.get(e);
  if (!o) {
    pt++;
    return;
  }
  const f = (u) => {
    u && u.trigger();
  };
  if (Es(), t === "clear")
    o.forEach(f);
  else {
    const u = P(e), h = u && vs(s);
    if (u && s === "length") {
      const a = Number(n);
      o.forEach((p, w) => {
        (w === "length" || w === gt || !Fe(w) && w >= a) && f(p);
      });
    } else
      switch ((s !== void 0 || o.has(void 0)) && f(o.get(s)), h && f(o.get(gt)), t) {
        case "add":
          u ? h && f(o.get("length")) : (f(o.get(Ke)), ze(e) && f(o.get(cs)));
          break;
        case "delete":
          u || (f(o.get(Ke)), ze(e) && f(o.get(cs)));
          break;
        case "set":
          ze(e) && f(o.get(Ke));
          break;
      }
  }
  Ts();
}
function qe(e) {
  const t = $(e);
  return t === e ? t : (z(t, "iterate", gt), xe(e) ? t : t.map(le));
}
function Os(e) {
  return z(e = $(e), "iterate", gt), e;
}
const Vi = {
  __proto__: null,
  [Symbol.iterator]() {
    return kt(this, Symbol.iterator, le);
  },
  concat(...e) {
    return qe(this).concat(
      ...e.map((t) => P(t) ? qe(t) : t)
    );
  },
  entries() {
    return kt(this, "entries", (e) => (e[1] = le(e[1]), e));
  },
  every(e, t) {
    return Se(this, "every", e, t, void 0, arguments);
  },
  filter(e, t) {
    return Se(this, "filter", e, t, (s) => s.map(le), arguments);
  },
  find(e, t) {
    return Se(this, "find", e, t, le, arguments);
  },
  findIndex(e, t) {
    return Se(this, "findIndex", e, t, void 0, arguments);
  },
  findLast(e, t) {
    return Se(this, "findLast", e, t, le, arguments);
  },
  findLastIndex(e, t) {
    return Se(this, "findLastIndex", e, t, void 0, arguments);
  },
  // flat, flatMap could benefit from ARRAY_ITERATE but are not straight-forward to implement
  forEach(e, t) {
    return Se(this, "forEach", e, t, void 0, arguments);
  },
  includes(...e) {
    return es(this, "includes", e);
  },
  indexOf(...e) {
    return es(this, "indexOf", e);
  },
  join(e) {
    return qe(this).join(e);
  },
  // keys() iterator only reads `length`, no optimisation required
  lastIndexOf(...e) {
    return es(this, "lastIndexOf", e);
  },
  map(e, t) {
    return Se(this, "map", e, t, void 0, arguments);
  },
  pop() {
    return it(this, "pop");
  },
  push(...e) {
    return it(this, "push", e);
  },
  reduce(e, ...t) {
    return Js(this, "reduce", e, t);
  },
  reduceRight(e, ...t) {
    return Js(this, "reduceRight", e, t);
  },
  shift() {
    return it(this, "shift");
  },
  // slice could use ARRAY_ITERATE but also seems to beg for range tracking
  some(e, t) {
    return Se(this, "some", e, t, void 0, arguments);
  },
  splice(...e) {
    return it(this, "splice", e);
  },
  toReversed() {
    return qe(this).toReversed();
  },
  toSorted(e) {
    return qe(this).toSorted(e);
  },
  toSpliced(...e) {
    return qe(this).toSpliced(...e);
  },
  unshift(...e) {
    return it(this, "unshift", e);
  },
  values() {
    return kt(this, "values", le);
  }
};
function kt(e, t, s) {
  const n = Os(e), i = n[t]();
  return n !== e && !xe(e) && (i._next = i.next, i.next = () => {
    const r = i._next();
    return r.value && (r.value = s(r.value)), r;
  }), i;
}
const Ui = Array.prototype;
function Se(e, t, s, n, i, r) {
  const o = Os(e), f = o !== e && !xe(e), u = o[t];
  if (u !== Ui[t]) {
    const p = u.apply(e, r);
    return f ? le(p) : p;
  }
  let h = s;
  o !== e && (f ? h = function(p, w) {
    return s.call(this, le(p), w, e);
  } : s.length > 2 && (h = function(p, w) {
    return s.call(this, p, w, e);
  }));
  const a = u.call(o, h, n);
  return f && i ? i(a) : a;
}
function Js(e, t, s, n) {
  const i = Os(e);
  let r = s;
  return i !== e && (xe(e) ? s.length > 3 && (r = function(o, f, u) {
    return s.call(this, o, f, u, e);
  }) : r = function(o, f, u) {
    return s.call(this, o, le(f), u, e);
  }), i[t](r, ...n);
}
function es(e, t, s) {
  const n = $(e);
  z(n, "iterate", gt);
  const i = n[t](...s);
  return (i === -1 || i === !1) && Is(s[0]) ? (s[0] = $(s[0]), n[t](...s)) : i;
}
function it(e, t, s = []) {
  De(), Es();
  const n = $(e)[t].apply(e, s);
  return Ts(), je(), n;
}
const Bi = /* @__PURE__ */ bs("__proto__,__v_isRef,__isVue"), $n = new Set(
  /* @__PURE__ */ Object.getOwnPropertyNames(Symbol).filter((e) => e !== "arguments" && e !== "caller").map((e) => Symbol[e]).filter(Fe)
);
function Ki(e) {
  Fe(e) || (e = String(e));
  const t = $(this);
  return z(t, "has", e), t.hasOwnProperty(e);
}
class Hn {
  constructor(t = !1, s = !1) {
    this._isReadonly = t, this._isShallow = s;
  }
  get(t, s, n) {
    if (s === "__v_skip") return t.__v_skip;
    const i = this._isReadonly, r = this._isShallow;
    if (s === "__v_isReactive")
      return !i;
    if (s === "__v_isReadonly")
      return i;
    if (s === "__v_isShallow")
      return r;
    if (s === "__v_raw")
      return n === (i ? r ? ki : Un : r ? Vn : Ln).get(t) || // receiver is not the reactive proxy, but has the same prototype
      // this means the receiver is a user proxy of the reactive proxy
      Object.getPrototypeOf(t) === Object.getPrototypeOf(n) ? t : void 0;
    const o = P(t);
    if (!i) {
      let u;
      if (o && (u = Vi[s]))
        return u;
      if (s === "hasOwnProperty")
        return Ki;
    }
    const f = Reflect.get(
      t,
      s,
      // if this is a proxy wrapping a ref, return methods using the raw ref
      // as receiver so that we don't have to call `toRaw` on the ref in all
      // its class methods
      ee(t) ? t : n
    );
    return (Fe(s) ? $n.has(s) : Bi(s)) || (i || z(t, "get", s), r) ? f : ee(f) ? o && vs(s) ? f : f.value : J(f) ? i ? Bn(f) : Ps(f) : f;
  }
}
class Nn extends Hn {
  constructor(t = !1) {
    super(!1, t);
  }
  set(t, s, n, i) {
    let r = t[s];
    if (!this._isShallow) {
      const u = Qe(r);
      if (!xe(n) && !Qe(n) && (r = $(r), n = $(n)), !P(t) && ee(r) && !ee(n))
        return u ? !1 : (r.value = n, !0);
    }
    const o = P(t) && vs(s) ? Number(s) < t.length : D(t, s), f = Reflect.set(
      t,
      s,
      n,
      ee(t) ? t : i
    );
    return t === $(i) && (o ? Be(n, r) && Te(t, "set", s, n) : Te(t, "add", s, n)), f;
  }
  deleteProperty(t, s) {
    const n = D(t, s);
    t[s];
    const i = Reflect.deleteProperty(t, s);
    return i && n && Te(t, "delete", s, void 0), i;
  }
  has(t, s) {
    const n = Reflect.has(t, s);
    return (!Fe(s) || !$n.has(s)) && z(t, "has", s), n;
  }
  ownKeys(t) {
    return z(
      t,
      "iterate",
      P(t) ? "length" : Ke
    ), Reflect.ownKeys(t);
  }
}
class Wi extends Hn {
  constructor(t = !1) {
    super(!0, t);
  }
  set(t, s) {
    return !0;
  }
  deleteProperty(t, s) {
    return !0;
  }
}
const Ji = /* @__PURE__ */ new Nn(), qi = /* @__PURE__ */ new Wi(), Gi = /* @__PURE__ */ new Nn(!0);
const us = (e) => e, Ot = (e) => Reflect.getPrototypeOf(e);
function Yi(e, t, s) {
  return function(...n) {
    const i = this.__v_raw, r = $(i), o = ze(r), f = e === "entries" || e === Symbol.iterator && o, u = e === "keys" && o, h = i[e](...n), a = s ? us : t ? as : le;
    return !t && z(
      r,
      "iterate",
      u ? cs : Ke
    ), {
      // iterator protocol
      next() {
        const { value: p, done: w } = h.next();
        return w ? { value: p, done: w } : {
          value: f ? [a(p[0]), a(p[1])] : a(p),
          done: w
        };
      },
      // iterable protocol
      [Symbol.iterator]() {
        return this;
      }
    };
  };
}
function At(e) {
  return function(...t) {
    return e === "delete" ? !1 : e === "clear" ? void 0 : this;
  };
}
function zi(e, t) {
  const s = {
    get(i) {
      const r = this.__v_raw, o = $(r), f = $(i);
      e || (Be(i, f) && z(o, "get", i), z(o, "get", f));
      const { has: u } = Ot(o), h = t ? us : e ? as : le;
      if (u.call(o, i))
        return h(r.get(i));
      if (u.call(o, f))
        return h(r.get(f));
      r !== o && r.get(i);
    },
    get size() {
      const i = this.__v_raw;
      return !e && z($(i), "iterate", Ke), Reflect.get(i, "size", i);
    },
    has(i) {
      const r = this.__v_raw, o = $(r), f = $(i);
      return e || (Be(i, f) && z(o, "has", i), z(o, "has", f)), i === f ? r.has(i) : r.has(i) || r.has(f);
    },
    forEach(i, r) {
      const o = this, f = o.__v_raw, u = $(f), h = t ? us : e ? as : le;
      return !e && z(u, "iterate", Ke), f.forEach((a, p) => i.call(r, h(a), h(p), o));
    }
  };
  return te(
    s,
    e ? {
      add: At("add"),
      set: At("set"),
      delete: At("delete"),
      clear: At("clear")
    } : {
      add(i) {
        !t && !xe(i) && !Qe(i) && (i = $(i));
        const r = $(this);
        return Ot(r).has.call(r, i) || (r.add(i), Te(r, "add", i, i)), this;
      },
      set(i, r) {
        !t && !xe(r) && !Qe(r) && (r = $(r));
        const o = $(this), { has: f, get: u } = Ot(o);
        let h = f.call(o, i);
        h || (i = $(i), h = f.call(o, i));
        const a = u.call(o, i);
        return o.set(i, r), h ? Be(r, a) && Te(o, "set", i, r) : Te(o, "add", i, r), this;
      },
      delete(i) {
        const r = $(this), { has: o, get: f } = Ot(r);
        let u = o.call(r, i);
        u || (i = $(i), u = o.call(r, i)), f && f.call(r, i);
        const h = r.delete(i);
        return u && Te(r, "delete", i, void 0), h;
      },
      clear() {
        const i = $(this), r = i.size !== 0, o = i.clear();
        return r && Te(
          i,
          "clear",
          void 0,
          void 0
        ), o;
      }
    }
  ), [
    "keys",
    "values",
    "entries",
    Symbol.iterator
  ].forEach((i) => {
    s[i] = Yi(i, e, t);
  }), s;
}
function As(e, t) {
  const s = zi(e, t);
  return (n, i, r) => i === "__v_isReactive" ? !e : i === "__v_isReadonly" ? e : i === "__v_raw" ? n : Reflect.get(
    D(s, i) && i in n ? s : n,
    i,
    r
  );
}
const Xi = {
  get: /* @__PURE__ */ As(!1, !1)
}, Zi = {
  get: /* @__PURE__ */ As(!1, !0)
}, Qi = {
  get: /* @__PURE__ */ As(!0, !1)
};
const Ln = /* @__PURE__ */ new WeakMap(), Vn = /* @__PURE__ */ new WeakMap(), Un = /* @__PURE__ */ new WeakMap(), ki = /* @__PURE__ */ new WeakMap();
function er(e) {
  switch (e) {
    case "Object":
    case "Array":
      return 1;
    case "Map":
    case "Set":
    case "WeakMap":
    case "WeakSet":
      return 2;
    default:
      return 0;
  }
}
function tr(e) {
  return e.__v_skip || !Object.isExtensible(e) ? 0 : er(Ci(e));
}
function Ps(e) {
  return Qe(e) ? e : Rs(
    e,
    !1,
    Ji,
    Xi,
    Ln
  );
}
function sr(e) {
  return Rs(
    e,
    !1,
    Gi,
    Zi,
    Vn
  );
}
function Bn(e) {
  return Rs(
    e,
    !0,
    qi,
    Qi,
    Un
  );
}
function Rs(e, t, s, n, i) {
  if (!J(e) || e.__v_raw && !(t && e.__v_isReactive))
    return e;
  const r = i.get(e);
  if (r)
    return r;
  const o = tr(e);
  if (o === 0)
    return e;
  const f = new Proxy(
    e,
    o === 2 ? n : s
  );
  return i.set(e, f), f;
}
function ut(e) {
  return Qe(e) ? ut(e.__v_raw) : !!(e && e.__v_isReactive);
}
function Qe(e) {
  return !!(e && e.__v_isReadonly);
}
function xe(e) {
  return !!(e && e.__v_isShallow);
}
function Is(e) {
  return e ? !!e.__v_raw : !1;
}
function $(e) {
  const t = e && e.__v_raw;
  return t ? $(t) : e;
}
function nr(e) {
  return !D(e, "__v_skip") && Object.isExtensible(e) && Sn(e, "__v_skip", !0), e;
}
const le = (e) => J(e) ? Ps(e) : e, as = (e) => J(e) ? Bn(e) : e;
function ee(e) {
  return e ? e.__v_isRef === !0 : !1;
}
function ir(e) {
  return ee(e) ? e.value : e;
}
const rr = {
  get: (e, t, s) => t === "__v_raw" ? e : ir(Reflect.get(e, t, s)),
  set: (e, t, s, n) => {
    const i = e[t];
    return ee(i) && !ee(s) ? (i.value = s, !0) : Reflect.set(e, t, s, n);
  }
};
function Kn(e) {
  return ut(e) ? e : new Proxy(e, rr);
}
class or {
  constructor(t, s, n) {
    this.fn = t, this.setter = s, this._value = void 0, this.dep = new Dn(this), this.__v_isRef = !0, this.deps = void 0, this.depsTail = void 0, this.flags = 16, this.globalVersion = pt - 1, this.next = void 0, this.effect = this, this.__v_isReadonly = !s, this.isSSR = n;
  }
  /**
   * @internal
   */
  notify() {
    if (this.flags |= 16, !(this.flags & 8) && // avoid infinite self recursion
    V !== this)
      return Pn(this, !0), !0;
  }
  get value() {
    const t = this.dep.track();
    return Mn(this), t && (t.version = this.dep.version), this._value;
  }
  set value(t) {
    this.setter && this.setter(t);
  }
}
function lr(e, t, s = !1) {
  let n, i;
  return R(e) ? n = e : (n = e.get, i = e.set), new or(n, i, s);
}
const Pt = {}, Ft = /* @__PURE__ */ new WeakMap();
let Ue;
function fr(e, t = !1, s = Ue) {
  if (s) {
    let n = Ft.get(s);
    n || Ft.set(s, n = []), n.push(e);
  }
}
function cr(e, t, s = U) {
  const { immediate: n, deep: i, once: r, scheduler: o, augmentJob: f, call: u } = s, h = (O) => i ? O : xe(O) || i === !1 || i === 0 ? Ie(O, 1) : Ie(O);
  let a, p, w, E, F = !1, M = !1;
  if (ee(e) ? (p = () => e.value, F = xe(e)) : ut(e) ? (p = () => h(e), F = !0) : P(e) ? (M = !0, F = e.some((O) => ut(O) || xe(O)), p = () => e.map((O) => {
    if (ee(O))
      return O.value;
    if (ut(O))
      return h(O);
    if (R(O))
      return u ? u(O, 2) : O();
  })) : R(e) ? t ? p = u ? () => u(e, 2) : e : p = () => {
    if (w) {
      De();
      try {
        w();
      } finally {
        je();
      }
    }
    const O = Ue;
    Ue = a;
    try {
      return u ? u(e, 3, [E]) : e(E);
    } finally {
      Ue = O;
    }
  } : p = ye, t && i) {
    const O = p, q = i === !0 ? 1 / 0 : i;
    p = () => Ie(O(), q);
  }
  const Y = Hi(), H = () => {
    a.stop(), Y && Y.active && xs(Y.effects, a);
  };
  if (r && t) {
    const O = t;
    t = (...q) => {
      O(...q), H();
    };
  }
  let K = M ? new Array(e.length).fill(Pt) : Pt;
  const W = (O) => {
    if (!(!(a.flags & 1) || !a.dirty && !O))
      if (t) {
        const q = a.run();
        if (i || F || (M ? q.some((Oe, ue) => Be(Oe, K[ue])) : Be(q, K))) {
          w && w();
          const Oe = Ue;
          Ue = a;
          try {
            const ue = [
              q,
              // pass undefined as the old value when it's changed for the first time
              K === Pt ? void 0 : M && K[0] === Pt ? [] : K,
              E
            ];
            u ? u(t, 3, ue) : (
              // @ts-expect-error
              t(...ue)
            ), K = q;
          } finally {
            Ue = Oe;
          }
        }
      } else
        a.run();
  };
  return f && f(W), a = new On(p), a.scheduler = o ? () => o(W, !1) : W, E = (O) => fr(O, !1, a), w = a.onStop = () => {
    const O = Ft.get(a);
    if (O) {
      if (u)
        u(O, 4);
      else
        for (const q of O) q();
      Ft.delete(a);
    }
  }, t ? n ? W(!0) : K = a.run() : o ? o(W.bind(null, !0), !0) : a.run(), H.pause = a.pause.bind(a), H.resume = a.resume.bind(a), H.stop = H, H;
}
function Ie(e, t = 1 / 0, s) {
  if (t <= 0 || !J(e) || e.__v_skip || (s = s || /* @__PURE__ */ new Set(), s.has(e)))
    return e;
  if (s.add(e), t--, ee(e))
    Ie(e.value, t, s);
  else if (P(e))
    for (let n = 0; n < e.length; n++)
      Ie(e[n], t, s);
  else if (mn(e) || ze(e))
    e.forEach((n) => {
      Ie(n, t, s);
    });
  else if (xn(e)) {
    for (const n in e)
      Ie(e[n], t, s);
    for (const n of Object.getOwnPropertySymbols(e))
      Object.prototype.propertyIsEnumerable.call(e, n) && Ie(e[n], t, s);
  }
  return e;
}
/**
* @vue/runtime-core v3.5.13
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
function xt(e, t, s, n) {
  try {
    return n ? e(...n) : e();
  } catch (i) {
    Kt(i, t, s);
  }
}
function ve(e, t, s, n) {
  if (R(e)) {
    const i = xt(e, t, s, n);
    return i && bn(i) && i.catch((r) => {
      Kt(r, t, s);
    }), i;
  }
  if (P(e)) {
    const i = [];
    for (let r = 0; r < e.length; r++)
      i.push(ve(e[r], t, s, n));
    return i;
  }
}
function Kt(e, t, s, n = !0) {
  const i = t ? t.vnode : null, { errorHandler: r, throwUnhandledErrorInProduction: o } = t && t.appContext.config || U;
  if (t) {
    let f = t.parent;
    const u = t.proxy, h = `https://vuejs.org/error-reference/#runtime-${s}`;
    for (; f; ) {
      const a = f.ec;
      if (a) {
        for (let p = 0; p < a.length; p++)
          if (a[p](e, u, h) === !1)
            return;
      }
      f = f.parent;
    }
    if (r) {
      De(), xt(r, null, 10, [
        e,
        u,
        h
      ]), je();
      return;
    }
  }
  ur(e, s, i, n, o);
}
function ur(e, t, s, n = !0, i = !1) {
  if (i)
    throw e;
  console.error(e);
}
const Q = [];
let _e = -1;
const Xe = [];
let Pe = null, Ge = 0;
const Wn = /* @__PURE__ */ Promise.resolve();
let Dt = null;
function ar(e) {
  const t = Dt || Wn;
  return e ? t.then(this ? e.bind(this) : e) : t;
}
function dr(e) {
  let t = _e + 1, s = Q.length;
  for (; t < s; ) {
    const n = t + s >>> 1, i = Q[n], r = _t(i);
    r < e || r === e && i.flags & 2 ? t = n + 1 : s = n;
  }
  return t;
}
function Ms(e) {
  if (!(e.flags & 1)) {
    const t = _t(e), s = Q[Q.length - 1];
    !s || // fast path when the job id is larger than the tail
    !(e.flags & 2) && t >= _t(s) ? Q.push(e) : Q.splice(dr(t), 0, e), e.flags |= 1, Jn();
  }
}
function Jn() {
  Dt || (Dt = Wn.then(Gn));
}
function hr(e) {
  P(e) ? Xe.push(...e) : Pe && e.id === -1 ? Pe.splice(Ge + 1, 0, e) : e.flags & 1 || (Xe.push(e), e.flags |= 1), Jn();
}
function qs(e, t, s = _e + 1) {
  for (; s < Q.length; s++) {
    const n = Q[s];
    if (n && n.flags & 2) {
      if (e && n.id !== e.uid)
        continue;
      Q.splice(s, 1), s--, n.flags & 4 && (n.flags &= -2), n(), n.flags & 4 || (n.flags &= -2);
    }
  }
}
function qn(e) {
  if (Xe.length) {
    const t = [...new Set(Xe)].sort(
      (s, n) => _t(s) - _t(n)
    );
    if (Xe.length = 0, Pe) {
      Pe.push(...t);
      return;
    }
    for (Pe = t, Ge = 0; Ge < Pe.length; Ge++) {
      const s = Pe[Ge];
      s.flags & 4 && (s.flags &= -2), s.flags & 8 || s(), s.flags &= -2;
    }
    Pe = null, Ge = 0;
  }
}
const _t = (e) => e.id == null ? e.flags & 2 ? -1 : 1 / 0 : e.id;
function Gn(e) {
  try {
    for (_e = 0; _e < Q.length; _e++) {
      const t = Q[_e];
      t && !(t.flags & 8) && (t.flags & 4 && (t.flags &= -2), xt(
        t,
        t.i,
        t.i ? 15 : 14
      ), t.flags & 4 || (t.flags &= -2));
    }
  } finally {
    for (; _e < Q.length; _e++) {
      const t = Q[_e];
      t && (t.flags &= -2);
    }
    _e = -1, Q.length = 0, qn(), Dt = null, (Q.length || Xe.length) && Gn();
  }
}
let be = null, Yn = null;
function jt(e) {
  const t = be;
  return be = e, Yn = e && e.type.__scopeId || null, t;
}
function pr(e, t = be, s) {
  if (!t || e._n)
    return e;
  const n = (...i) => {
    n._d && tn(-1);
    const r = jt(t);
    let o;
    try {
      o = e(...i);
    } finally {
      jt(r), n._d && tn(1);
    }
    return o;
  };
  return n._n = !0, n._c = !0, n._d = !0, n;
}
function Le(e, t, s, n) {
  const i = e.dirs, r = t && t.dirs;
  for (let o = 0; o < i.length; o++) {
    const f = i[o];
    r && (f.oldValue = r[o].value);
    let u = f.dir[n];
    u && (De(), ve(u, s, 8, [
      e.el,
      f,
      e,
      t
    ]), je());
  }
}
const gr = Symbol("_vte"), _r = (e) => e.__isTeleport;
function Fs(e, t) {
  e.shapeFlag & 6 && e.component ? (e.transition = t, Fs(e.component.subTree, t)) : e.shapeFlag & 128 ? (e.ssContent.transition = t.clone(e.ssContent), e.ssFallback.transition = t.clone(e.ssFallback)) : e.transition = t;
}
function zn(e) {
  e.ids = [e.ids[0] + e.ids[2]++ + "-", 0, 0];
}
function $t(e, t, s, n, i = !1) {
  if (P(e)) {
    e.forEach(
      (F, M) => $t(
        F,
        t && (P(t) ? t[M] : t),
        s,
        n,
        i
      )
    );
    return;
  }
  if (at(n) && !i) {
    n.shapeFlag & 512 && n.type.__asyncResolved && n.component.subTree.component && $t(e, t, s, n.component.subTree);
    return;
  }
  const r = n.shapeFlag & 4 ? Hs(n.component) : n.el, o = i ? null : r, { i: f, r: u } = e, h = t && t.r, a = f.refs === U ? f.refs = {} : f.refs, p = f.setupState, w = $(p), E = p === U ? () => !1 : (F) => D(w, F);
  if (h != null && h !== u && (G(h) ? (a[h] = null, E(h) && (p[h] = null)) : ee(h) && (h.value = null)), R(u))
    xt(u, f, 12, [o, a]);
  else {
    const F = G(u), M = ee(u);
    if (F || M) {
      const Y = () => {
        if (e.f) {
          const H = F ? E(u) ? p[u] : a[u] : u.value;
          i ? P(H) && xs(H, r) : P(H) ? H.includes(r) || H.push(r) : F ? (a[u] = [r], E(u) && (p[u] = a[u])) : (u.value = [r], e.k && (a[e.k] = u.value));
        } else F ? (a[u] = o, E(u) && (p[u] = o)) : M && (u.value = o, e.k && (a[e.k] = o));
      };
      o ? (Y.id = -1, re(Y, s)) : Y();
    }
  }
}
Bt().requestIdleCallback;
Bt().cancelIdleCallback;
const at = (e) => !!e.type.__asyncLoader, Xn = (e) => e.type.__isKeepAlive;
function mr(e, t) {
  Zn(e, "a", t);
}
function br(e, t) {
  Zn(e, "da", t);
}
function Zn(e, t, s = k) {
  const n = e.__wdc || (e.__wdc = () => {
    let i = s;
    for (; i; ) {
      if (i.isDeactivated)
        return;
      i = i.parent;
    }
    return e();
  });
  if (Wt(t, n, s), s) {
    let i = s.parent;
    for (; i && i.parent; )
      Xn(i.parent.vnode) && yr(n, t, s, i), i = i.parent;
  }
}
function yr(e, t, s, n) {
  const i = Wt(
    t,
    e,
    n,
    !0
    /* prepend */
  );
  Qn(() => {
    xs(n[t], i);
  }, s);
}
function Wt(e, t, s = k, n = !1) {
  if (s) {
    const i = s[e] || (s[e] = []), r = t.__weh || (t.__weh = (...o) => {
      De();
      const f = vt(s), u = ve(t, s, e, o);
      return f(), je(), u;
    });
    return n ? i.unshift(r) : i.push(r), r;
  }
}
const Ce = (e) => (t, s = k) => {
  (!yt || e === "sp") && Wt(e, (...n) => t(...n), s);
}, xr = Ce("bm"), vr = Ce("m"), Sr = Ce(
  "bu"
), wr = Ce("u"), Er = Ce(
  "bum"
), Qn = Ce("um"), Tr = Ce(
  "sp"
), Cr = Ce("rtg"), Or = Ce("rtc");
function Ar(e, t = k) {
  Wt("ec", e, t);
}
const Pr = Symbol.for("v-ndc"), ds = (e) => e ? yi(e) ? Hs(e) : ds(e.parent) : null, dt = (
  // Move PURE marker to new line to workaround compiler discarding it
  // due to type annotation
  /* @__PURE__ */ te(/* @__PURE__ */ Object.create(null), {
    $: (e) => e,
    $el: (e) => e.vnode.el,
    $data: (e) => e.data,
    $props: (e) => e.props,
    $attrs: (e) => e.attrs,
    $slots: (e) => e.slots,
    $refs: (e) => e.refs,
    $parent: (e) => ds(e.parent),
    $root: (e) => ds(e.root),
    $host: (e) => e.ce,
    $emit: (e) => e.emit,
    $options: (e) => ei(e),
    $forceUpdate: (e) => e.f || (e.f = () => {
      Ms(e.update);
    }),
    $nextTick: (e) => e.n || (e.n = ar.bind(e.proxy)),
    $watch: (e) => Zr.bind(e)
  })
), ts = (e, t) => e !== U && !e.__isScriptSetup && D(e, t), Rr = {
  get({ _: e }, t) {
    if (t === "__v_skip")
      return !0;
    const { ctx: s, setupState: n, data: i, props: r, accessCache: o, type: f, appContext: u } = e;
    let h;
    if (t[0] !== "$") {
      const E = o[t];
      if (E !== void 0)
        switch (E) {
          case 1:
            return n[t];
          case 2:
            return i[t];
          case 4:
            return s[t];
          case 3:
            return r[t];
        }
      else {
        if (ts(n, t))
          return o[t] = 1, n[t];
        if (i !== U && D(i, t))
          return o[t] = 2, i[t];
        if (
          // only cache other properties when instance has declared (thus stable)
          // props
          (h = e.propsOptions[0]) && D(h, t)
        )
          return o[t] = 3, r[t];
        if (s !== U && D(s, t))
          return o[t] = 4, s[t];
        hs && (o[t] = 0);
      }
    }
    const a = dt[t];
    let p, w;
    if (a)
      return t === "$attrs" && z(e.attrs, "get", ""), a(e);
    if (
      // css module (injected by vue-loader)
      (p = f.__cssModules) && (p = p[t])
    )
      return p;
    if (s !== U && D(s, t))
      return o[t] = 4, s[t];
    if (
      // global properties
      w = u.config.globalProperties, D(w, t)
    )
      return w[t];
  },
  set({ _: e }, t, s) {
    const { data: n, setupState: i, ctx: r } = e;
    return ts(i, t) ? (i[t] = s, !0) : n !== U && D(n, t) ? (n[t] = s, !0) : D(e.props, t) || t[0] === "$" && t.slice(1) in e ? !1 : (r[t] = s, !0);
  },
  has({
    _: { data: e, setupState: t, accessCache: s, ctx: n, appContext: i, propsOptions: r }
  }, o) {
    let f;
    return !!s[o] || e !== U && D(e, o) || ts(t, o) || (f = r[0]) && D(f, o) || D(n, o) || D(dt, o) || D(i.config.globalProperties, o);
  },
  defineProperty(e, t, s) {
    return s.get != null ? e._.accessCache[t] = 0 : D(s, "value") && this.set(e, t, s.value, null), Reflect.defineProperty(e, t, s);
  }
};
function Gs(e) {
  return P(e) ? e.reduce(
    (t, s) => (t[s] = null, t),
    {}
  ) : e;
}
let hs = !0;
function Ir(e) {
  const t = ei(e), s = e.proxy, n = e.ctx;
  hs = !1, t.beforeCreate && Ys(t.beforeCreate, e, "bc");
  const {
    // state
    data: i,
    computed: r,
    methods: o,
    watch: f,
    provide: u,
    inject: h,
    // lifecycle
    created: a,
    beforeMount: p,
    mounted: w,
    beforeUpdate: E,
    updated: F,
    activated: M,
    deactivated: Y,
    beforeDestroy: H,
    beforeUnmount: K,
    destroyed: W,
    unmounted: O,
    render: q,
    renderTracked: Oe,
    renderTriggered: ue,
    errorCaptured: Ae,
    serverPrefetch: St,
    // public API
    expose: $e,
    inheritAttrs: et,
    // assets
    components: wt,
    directives: Et,
    filters: Gt
  } = t;
  if (h && Mr(h, n, null), o)
    for (const B in o) {
      const N = o[B];
      R(N) && (n[B] = N.bind(s));
    }
  if (i) {
    const B = i.call(s, s);
    J(B) && (e.data = Ps(B));
  }
  if (hs = !0, r)
    for (const B in r) {
      const N = r[B], He = R(N) ? N.bind(s, s) : R(N.get) ? N.get.bind(s, s) : ye, Tt = !R(N) && R(N.set) ? N.set.bind(s) : ye, Ne = So({
        get: He,
        set: Tt
      });
      Object.defineProperty(n, B, {
        enumerable: !0,
        configurable: !0,
        get: () => Ne.value,
        set: (ae) => Ne.value = ae
      });
    }
  if (f)
    for (const B in f)
      kn(f[B], n, s, B);
  if (u) {
    const B = R(u) ? u.call(s) : u;
    Reflect.ownKeys(B).forEach((N) => {
      Nr(N, B[N]);
    });
  }
  a && Ys(a, e, "c");
  function X(B, N) {
    P(N) ? N.forEach((He) => B(He.bind(s))) : N && B(N.bind(s));
  }
  if (X(xr, p), X(vr, w), X(Sr, E), X(wr, F), X(mr, M), X(br, Y), X(Ar, Ae), X(Or, Oe), X(Cr, ue), X(Er, K), X(Qn, O), X(Tr, St), P($e))
    if ($e.length) {
      const B = e.exposed || (e.exposed = {});
      $e.forEach((N) => {
        Object.defineProperty(B, N, {
          get: () => s[N],
          set: (He) => s[N] = He
        });
      });
    } else e.exposed || (e.exposed = {});
  q && e.render === ye && (e.render = q), et != null && (e.inheritAttrs = et), wt && (e.components = wt), Et && (e.directives = Et), St && zn(e);
}
function Mr(e, t, s = ye) {
  P(e) && (e = ps(e));
  for (const n in e) {
    const i = e[n];
    let r;
    J(i) ? "default" in i ? r = Rt(
      i.from || n,
      i.default,
      !0
    ) : r = Rt(i.from || n) : r = Rt(i), ee(r) ? Object.defineProperty(t, n, {
      enumerable: !0,
      configurable: !0,
      get: () => r.value,
      set: (o) => r.value = o
    }) : t[n] = r;
  }
}
function Ys(e, t, s) {
  ve(
    P(e) ? e.map((n) => n.bind(t.proxy)) : e.bind(t.proxy),
    t,
    s
  );
}
function kn(e, t, s, n) {
  let i = n.includes(".") ? pi(s, n) : () => s[n];
  if (G(e)) {
    const r = t[e];
    R(r) && ns(i, r);
  } else if (R(e))
    ns(i, e.bind(s));
  else if (J(e))
    if (P(e))
      e.forEach((r) => kn(r, t, s, n));
    else {
      const r = R(e.handler) ? e.handler.bind(s) : t[e.handler];
      R(r) && ns(i, r, e);
    }
}
function ei(e) {
  const t = e.type, { mixins: s, extends: n } = t, {
    mixins: i,
    optionsCache: r,
    config: { optionMergeStrategies: o }
  } = e.appContext, f = r.get(t);
  let u;
  return f ? u = f : !i.length && !s && !n ? u = t : (u = {}, i.length && i.forEach(
    (h) => Ht(u, h, o, !0)
  ), Ht(u, t, o)), J(t) && r.set(t, u), u;
}
function Ht(e, t, s, n = !1) {
  const { mixins: i, extends: r } = t;
  r && Ht(e, r, s, !0), i && i.forEach(
    (o) => Ht(e, o, s, !0)
  );
  for (const o in t)
    if (!(n && o === "expose")) {
      const f = Fr[o] || s && s[o];
      e[o] = f ? f(e[o], t[o]) : t[o];
    }
  return e;
}
const Fr = {
  data: zs,
  props: Xs,
  emits: Xs,
  // objects
  methods: ot,
  computed: ot,
  // lifecycle
  beforeCreate: Z,
  created: Z,
  beforeMount: Z,
  mounted: Z,
  beforeUpdate: Z,
  updated: Z,
  beforeDestroy: Z,
  beforeUnmount: Z,
  destroyed: Z,
  unmounted: Z,
  activated: Z,
  deactivated: Z,
  errorCaptured: Z,
  serverPrefetch: Z,
  // assets
  components: ot,
  directives: ot,
  // watch
  watch: jr,
  // provide / inject
  provide: zs,
  inject: Dr
};
function zs(e, t) {
  return t ? e ? function() {
    return te(
      R(e) ? e.call(this, this) : e,
      R(t) ? t.call(this, this) : t
    );
  } : t : e;
}
function Dr(e, t) {
  return ot(ps(e), ps(t));
}
function ps(e) {
  if (P(e)) {
    const t = {};
    for (let s = 0; s < e.length; s++)
      t[e[s]] = e[s];
    return t;
  }
  return e;
}
function Z(e, t) {
  return e ? [...new Set([].concat(e, t))] : t;
}
function ot(e, t) {
  return e ? te(/* @__PURE__ */ Object.create(null), e, t) : t;
}
function Xs(e, t) {
  return e ? P(e) && P(t) ? [.../* @__PURE__ */ new Set([...e, ...t])] : te(
    /* @__PURE__ */ Object.create(null),
    Gs(e),
    Gs(t ?? {})
  ) : t;
}
function jr(e, t) {
  if (!e) return t;
  if (!t) return e;
  const s = te(/* @__PURE__ */ Object.create(null), e);
  for (const n in t)
    s[n] = Z(e[n], t[n]);
  return s;
}
function ti() {
  return {
    app: null,
    config: {
      isNativeTag: Ei,
      performance: !1,
      globalProperties: {},
      optionMergeStrategies: {},
      errorHandler: void 0,
      warnHandler: void 0,
      compilerOptions: {}
    },
    mixins: [],
    components: {},
    directives: {},
    provides: /* @__PURE__ */ Object.create(null),
    optionsCache: /* @__PURE__ */ new WeakMap(),
    propsCache: /* @__PURE__ */ new WeakMap(),
    emitsCache: /* @__PURE__ */ new WeakMap()
  };
}
let $r = 0;
function Hr(e, t) {
  return function(n, i = null) {
    R(n) || (n = te({}, n)), i != null && !J(i) && (i = null);
    const r = ti(), o = /* @__PURE__ */ new WeakSet(), f = [];
    let u = !1;
    const h = r.app = {
      _uid: $r++,
      _component: n,
      _props: i,
      _container: null,
      _context: r,
      _instance: null,
      version: wo,
      get config() {
        return r.config;
      },
      set config(a) {
      },
      use(a, ...p) {
        return o.has(a) || (a && R(a.install) ? (o.add(a), a.install(h, ...p)) : R(a) && (o.add(a), a(h, ...p))), h;
      },
      mixin(a) {
        return r.mixins.includes(a) || r.mixins.push(a), h;
      },
      component(a, p) {
        return p ? (r.components[a] = p, h) : r.components[a];
      },
      directive(a, p) {
        return p ? (r.directives[a] = p, h) : r.directives[a];
      },
      mount(a, p, w) {
        if (!u) {
          const E = h._ceVNode || We(n, i);
          return E.appContext = r, w === !0 ? w = "svg" : w === !1 && (w = void 0), e(E, a, w), u = !0, h._container = a, a.__vue_app__ = h, Hs(E.component);
        }
      },
      onUnmount(a) {
        f.push(a);
      },
      unmount() {
        u && (ve(
          f,
          h._instance,
          16
        ), e(null, h._container), delete h._container.__vue_app__);
      },
      provide(a, p) {
        return r.provides[a] = p, h;
      },
      runWithContext(a) {
        const p = Ze;
        Ze = h;
        try {
          return a();
        } finally {
          Ze = p;
        }
      }
    };
    return h;
  };
}
let Ze = null;
function Nr(e, t) {
  if (k) {
    let s = k.provides;
    const n = k.parent && k.parent.provides;
    n === s && (s = k.provides = Object.create(n)), s[e] = t;
  }
}
function Rt(e, t, s = !1) {
  const n = k || be;
  if (n || Ze) {
    const i = Ze ? Ze._context.provides : n ? n.parent == null ? n.vnode.appContext && n.vnode.appContext.provides : n.parent.provides : void 0;
    if (i && e in i)
      return i[e];
    if (arguments.length > 1)
      return s && R(t) ? t.call(n && n.proxy) : t;
  }
}
const si = {}, ni = () => Object.create(si), ii = (e) => Object.getPrototypeOf(e) === si;
function Lr(e, t, s, n = !1) {
  const i = {}, r = ni();
  e.propsDefaults = /* @__PURE__ */ Object.create(null), ri(e, t, i, r);
  for (const o in e.propsOptions[0])
    o in i || (i[o] = void 0);
  s ? e.props = n ? i : sr(i) : e.type.props ? e.props = i : e.props = r, e.attrs = r;
}
function Vr(e, t, s, n) {
  const {
    props: i,
    attrs: r,
    vnode: { patchFlag: o }
  } = e, f = $(i), [u] = e.propsOptions;
  let h = !1;
  if (
    // always force full diff in dev
    // - #1942 if hmr is enabled with sfc component
    // - vite#872 non-sfc component used by sfc component
    (n || o > 0) && !(o & 16)
  ) {
    if (o & 8) {
      const a = e.vnode.dynamicProps;
      for (let p = 0; p < a.length; p++) {
        let w = a[p];
        if (Jt(e.emitsOptions, w))
          continue;
        const E = t[w];
        if (u)
          if (D(r, w))
            E !== r[w] && (r[w] = E, h = !0);
          else {
            const F = Me(w);
            i[F] = gs(
              u,
              f,
              F,
              E,
              e,
              !1
            );
          }
        else
          E !== r[w] && (r[w] = E, h = !0);
      }
    }
  } else {
    ri(e, t, i, r) && (h = !0);
    let a;
    for (const p in f)
      (!t || // for camelCase
      !D(t, p) && // it's possible the original props was passed in as kebab-case
      // and converted to camelCase (#955)
      ((a = Je(p)) === p || !D(t, a))) && (u ? s && // for camelCase
      (s[p] !== void 0 || // for kebab-case
      s[a] !== void 0) && (i[p] = gs(
        u,
        f,
        p,
        void 0,
        e,
        !0
      )) : delete i[p]);
    if (r !== f)
      for (const p in r)
        (!t || !D(t, p)) && (delete r[p], h = !0);
  }
  h && Te(e.attrs, "set", "");
}
function ri(e, t, s, n) {
  const [i, r] = e.propsOptions;
  let o = !1, f;
  if (t)
    for (let u in t) {
      if (lt(u))
        continue;
      const h = t[u];
      let a;
      i && D(i, a = Me(u)) ? !r || !r.includes(a) ? s[a] = h : (f || (f = {}))[a] = h : Jt(e.emitsOptions, u) || (!(u in n) || h !== n[u]) && (n[u] = h, o = !0);
    }
  if (r) {
    const u = $(s), h = f || U;
    for (let a = 0; a < r.length; a++) {
      const p = r[a];
      s[p] = gs(
        i,
        u,
        p,
        h[p],
        e,
        !D(h, p)
      );
    }
  }
  return o;
}
function gs(e, t, s, n, i, r) {
  const o = e[s];
  if (o != null) {
    const f = D(o, "default");
    if (f && n === void 0) {
      const u = o.default;
      if (o.type !== Function && !o.skipFactory && R(u)) {
        const { propsDefaults: h } = i;
        if (s in h)
          n = h[s];
        else {
          const a = vt(i);
          n = h[s] = u.call(
            null,
            t
          ), a();
        }
      } else
        n = u;
      i.ce && i.ce._setProp(s, n);
    }
    o[
      0
      /* shouldCast */
    ] && (r && !f ? n = !1 : o[
      1
      /* shouldCastTrue */
    ] && (n === "" || n === Je(s)) && (n = !0));
  }
  return n;
}
const Ur = /* @__PURE__ */ new WeakMap();
function oi(e, t, s = !1) {
  const n = s ? Ur : t.propsCache, i = n.get(e);
  if (i)
    return i;
  const r = e.props, o = {}, f = [];
  let u = !1;
  if (!R(e)) {
    const a = (p) => {
      u = !0;
      const [w, E] = oi(p, t, !0);
      te(o, w), E && f.push(...E);
    };
    !s && t.mixins.length && t.mixins.forEach(a), e.extends && a(e.extends), e.mixins && e.mixins.forEach(a);
  }
  if (!r && !u)
    return J(e) && n.set(e, Ye), Ye;
  if (P(r))
    for (let a = 0; a < r.length; a++) {
      const p = Me(r[a]);
      Zs(p) && (o[p] = U);
    }
  else if (r)
    for (const a in r) {
      const p = Me(a);
      if (Zs(p)) {
        const w = r[a], E = o[p] = P(w) || R(w) ? { type: w } : te({}, w), F = E.type;
        let M = !1, Y = !0;
        if (P(F))
          for (let H = 0; H < F.length; ++H) {
            const K = F[H], W = R(K) && K.name;
            if (W === "Boolean") {
              M = !0;
              break;
            } else W === "String" && (Y = !1);
          }
        else
          M = R(F) && F.name === "Boolean";
        E[
          0
          /* shouldCast */
        ] = M, E[
          1
          /* shouldCastTrue */
        ] = Y, (M || D(E, "default")) && f.push(p);
      }
    }
  const h = [o, f];
  return J(e) && n.set(e, h), h;
}
function Zs(e) {
  return e[0] !== "$" && !lt(e);
}
const li = (e) => e[0] === "_" || e === "$stable", Ds = (e) => P(e) ? e.map(me) : [me(e)], Br = (e, t, s) => {
  if (t._n)
    return t;
  const n = pr((...i) => Ds(t(...i)), s);
  return n._c = !1, n;
}, fi = (e, t, s) => {
  const n = e._ctx;
  for (const i in e) {
    if (li(i)) continue;
    const r = e[i];
    if (R(r))
      t[i] = Br(i, r, n);
    else if (r != null) {
      const o = Ds(r);
      t[i] = () => o;
    }
  }
}, ci = (e, t) => {
  const s = Ds(t);
  e.slots.default = () => s;
}, ui = (e, t, s) => {
  for (const n in t)
    (s || n !== "_") && (e[n] = t[n]);
}, Kr = (e, t, s) => {
  const n = e.slots = ni();
  if (e.vnode.shapeFlag & 32) {
    const i = t._;
    i ? (ui(n, t, s), s && Sn(n, "_", i, !0)) : fi(t, n);
  } else t && ci(e, t);
}, Wr = (e, t, s) => {
  const { vnode: n, slots: i } = e;
  let r = !0, o = U;
  if (n.shapeFlag & 32) {
    const f = t._;
    f ? s && f === 1 ? r = !1 : ui(i, t, s) : (r = !t.$stable, fi(t, i)), o = t;
  } else t && (ci(e, t), o = { default: 1 });
  if (r)
    for (const f in i)
      !li(f) && o[f] == null && delete i[f];
}, re = io;
function Jr(e) {
  return qr(e);
}
function qr(e, t) {
  const s = Bt();
  s.__VUE__ = !0;
  const {
    insert: n,
    remove: i,
    patchProp: r,
    createElement: o,
    createText: f,
    createComment: u,
    setText: h,
    setElementText: a,
    parentNode: p,
    nextSibling: w,
    setScopeId: E = ye,
    insertStaticContent: F
  } = e, M = (l, c, d, m = null, g = null, _ = null, v = void 0, x = null, y = !!c.dynamicChildren) => {
    if (l === c)
      return;
    l && !rt(l, c) && (m = Ct(l), ae(l, g, _, !0), l = null), c.patchFlag === -2 && (y = !1, c.dynamicChildren = null);
    const { type: b, ref: C, shapeFlag: S } = c;
    switch (b) {
      case qt:
        Y(l, c, d, m);
        break;
      case mt:
        H(l, c, d, m);
        break;
      case is:
        l == null && K(c, d, m, v);
        break;
      case Ee:
        wt(
          l,
          c,
          d,
          m,
          g,
          _,
          v,
          x,
          y
        );
        break;
      default:
        S & 1 ? q(
          l,
          c,
          d,
          m,
          g,
          _,
          v,
          x,
          y
        ) : S & 6 ? Et(
          l,
          c,
          d,
          m,
          g,
          _,
          v,
          x,
          y
        ) : (S & 64 || S & 128) && b.process(
          l,
          c,
          d,
          m,
          g,
          _,
          v,
          x,
          y,
          st
        );
    }
    C != null && g && $t(C, l && l.ref, _, c || l, !c);
  }, Y = (l, c, d, m) => {
    if (l == null)
      n(
        c.el = f(c.children),
        d,
        m
      );
    else {
      const g = c.el = l.el;
      c.children !== l.children && h(g, c.children);
    }
  }, H = (l, c, d, m) => {
    l == null ? n(
      c.el = u(c.children || ""),
      d,
      m
    ) : c.el = l.el;
  }, K = (l, c, d, m) => {
    [l.el, l.anchor] = F(
      l.children,
      c,
      d,
      m,
      l.el,
      l.anchor
    );
  }, W = ({ el: l, anchor: c }, d, m) => {
    let g;
    for (; l && l !== c; )
      g = w(l), n(l, d, m), l = g;
    n(c, d, m);
  }, O = ({ el: l, anchor: c }) => {
    let d;
    for (; l && l !== c; )
      d = w(l), i(l), l = d;
    i(c);
  }, q = (l, c, d, m, g, _, v, x, y) => {
    c.type === "svg" ? v = "svg" : c.type === "math" && (v = "mathml"), l == null ? Oe(
      c,
      d,
      m,
      g,
      _,
      v,
      x,
      y
    ) : St(
      l,
      c,
      g,
      _,
      v,
      x,
      y
    );
  }, Oe = (l, c, d, m, g, _, v, x) => {
    let y, b;
    const { props: C, shapeFlag: S, transition: T, dirs: A } = l;
    if (y = l.el = o(
      l.type,
      _,
      C && C.is,
      C
    ), S & 8 ? a(y, l.children) : S & 16 && Ae(
      l.children,
      y,
      null,
      m,
      g,
      ss(l, _),
      v,
      x
    ), A && Le(l, null, m, "created"), ue(y, l, l.scopeId, v, m), C) {
      for (const L in C)
        L !== "value" && !lt(L) && r(y, L, null, C[L], _, m);
      "value" in C && r(y, "value", null, C.value, _), (b = C.onVnodeBeforeMount) && ge(b, m, l);
    }
    A && Le(l, null, m, "beforeMount");
    const I = Gr(g, T);
    I && T.beforeEnter(y), n(y, c, d), ((b = C && C.onVnodeMounted) || I || A) && re(() => {
      b && ge(b, m, l), I && T.enter(y), A && Le(l, null, m, "mounted");
    }, g);
  }, ue = (l, c, d, m, g) => {
    if (d && E(l, d), m)
      for (let _ = 0; _ < m.length; _++)
        E(l, m[_]);
    if (g) {
      let _ = g.subTree;
      if (c === _ || _i(_.type) && (_.ssContent === c || _.ssFallback === c)) {
        const v = g.vnode;
        ue(
          l,
          v,
          v.scopeId,
          v.slotScopeIds,
          g.parent
        );
      }
    }
  }, Ae = (l, c, d, m, g, _, v, x, y = 0) => {
    for (let b = y; b < l.length; b++) {
      const C = l[b] = x ? Re(l[b]) : me(l[b]);
      M(
        null,
        C,
        c,
        d,
        m,
        g,
        _,
        v,
        x
      );
    }
  }, St = (l, c, d, m, g, _, v) => {
    const x = c.el = l.el;
    let { patchFlag: y, dynamicChildren: b, dirs: C } = c;
    y |= l.patchFlag & 16;
    const S = l.props || U, T = c.props || U;
    let A;
    if (d && Ve(d, !1), (A = T.onVnodeBeforeUpdate) && ge(A, d, c, l), C && Le(c, l, d, "beforeUpdate"), d && Ve(d, !0), (S.innerHTML && T.innerHTML == null || S.textContent && T.textContent == null) && a(x, ""), b ? $e(
      l.dynamicChildren,
      b,
      x,
      d,
      m,
      ss(c, g),
      _
    ) : v || N(
      l,
      c,
      x,
      null,
      d,
      m,
      ss(c, g),
      _,
      !1
    ), y > 0) {
      if (y & 16)
        et(x, S, T, d, g);
      else if (y & 2 && S.class !== T.class && r(x, "class", null, T.class, g), y & 4 && r(x, "style", S.style, T.style, g), y & 8) {
        const I = c.dynamicProps;
        for (let L = 0; L < I.length; L++) {
          const j = I[L], ne = S[j], se = T[j];
          (se !== ne || j === "value") && r(x, j, ne, se, g, d);
        }
      }
      y & 1 && l.children !== c.children && a(x, c.children);
    } else !v && b == null && et(x, S, T, d, g);
    ((A = T.onVnodeUpdated) || C) && re(() => {
      A && ge(A, d, c, l), C && Le(c, l, d, "updated");
    }, m);
  }, $e = (l, c, d, m, g, _, v) => {
    for (let x = 0; x < c.length; x++) {
      const y = l[x], b = c[x], C = (
        // oldVNode may be an errored async setup() component inside Suspense
        // which will not have a mounted element
        y.el && // - In the case of a Fragment, we need to provide the actual parent
        // of the Fragment itself so it can move its children.
        (y.type === Ee || // - In the case of different nodes, there is going to be a replacement
        // which also requires the correct parent container
        !rt(y, b) || // - In the case of a component, it could contain anything.
        y.shapeFlag & 70) ? p(y.el) : (
          // In other cases, the parent container is not actually used so we
          // just pass the block element here to avoid a DOM parentNode call.
          d
        )
      );
      M(
        y,
        b,
        C,
        null,
        m,
        g,
        _,
        v,
        !0
      );
    }
  }, et = (l, c, d, m, g) => {
    if (c !== d) {
      if (c !== U)
        for (const _ in c)
          !lt(_) && !(_ in d) && r(
            l,
            _,
            c[_],
            null,
            g,
            m
          );
      for (const _ in d) {
        if (lt(_)) continue;
        const v = d[_], x = c[_];
        v !== x && _ !== "value" && r(l, _, x, v, g, m);
      }
      "value" in d && r(l, "value", c.value, d.value, g);
    }
  }, wt = (l, c, d, m, g, _, v, x, y) => {
    const b = c.el = l ? l.el : f(""), C = c.anchor = l ? l.anchor : f("");
    let { patchFlag: S, dynamicChildren: T, slotScopeIds: A } = c;
    A && (x = x ? x.concat(A) : A), l == null ? (n(b, d, m), n(C, d, m), Ae(
      // #10007
      // such fragment like `<></>` will be compiled into
      // a fragment which doesn't have a children.
      // In this case fallback to an empty array
      c.children || [],
      d,
      C,
      g,
      _,
      v,
      x,
      y
    )) : S > 0 && S & 64 && T && // #2715 the previous fragment could've been a BAILed one as a result
    // of renderSlot() with no valid children
    l.dynamicChildren ? ($e(
      l.dynamicChildren,
      T,
      d,
      g,
      _,
      v,
      x
    ), // #2080 if the stable fragment has a key, it's a <template v-for> that may
    //  get moved around. Make sure all root level vnodes inherit el.
    // #2134 or if it's a component root, it may also get moved around
    // as the component is being moved.
    (c.key != null || g && c === g.subTree) && ai(
      l,
      c,
      !0
      /* shallow */
    )) : N(
      l,
      c,
      d,
      C,
      g,
      _,
      v,
      x,
      y
    );
  }, Et = (l, c, d, m, g, _, v, x, y) => {
    c.slotScopeIds = x, l == null ? c.shapeFlag & 512 ? g.ctx.activate(
      c,
      d,
      m,
      v,
      y
    ) : Gt(
      c,
      d,
      m,
      g,
      _,
      v,
      y
    ) : Ns(l, c, y);
  }, Gt = (l, c, d, m, g, _, v) => {
    const x = l.component = _o(
      l,
      m,
      g
    );
    if (Xn(l) && (x.ctx.renderer = st), mo(x, !1, v), x.asyncDep) {
      if (g && g.registerDep(x, X, v), !l.el) {
        const y = x.subTree = We(mt);
        H(null, y, c, d);
      }
    } else
      X(
        x,
        l,
        c,
        d,
        g,
        _,
        v
      );
  }, Ns = (l, c, d) => {
    const m = c.component = l.component;
    if (so(l, c, d))
      if (m.asyncDep && !m.asyncResolved) {
        B(m, c, d);
        return;
      } else
        m.next = c, m.update();
    else
      c.el = l.el, m.vnode = c;
  }, X = (l, c, d, m, g, _, v) => {
    const x = () => {
      if (l.isMounted) {
        let { next: S, bu: T, u: A, parent: I, vnode: L } = l;
        {
          const he = di(l);
          if (he) {
            S && (S.el = L.el, B(l, S, v)), he.asyncDep.then(() => {
              l.isUnmounted || x();
            });
            return;
          }
        }
        let j = S, ne;
        Ve(l, !1), S ? (S.el = L.el, B(l, S, v)) : S = L, T && Xt(T), (ne = S.props && S.props.onVnodeBeforeUpdate) && ge(ne, I, S, L), Ve(l, !0);
        const se = ks(l), de = l.subTree;
        l.subTree = se, M(
          de,
          se,
          // parent may have changed if it's in a teleport
          p(de.el),
          // anchor may have changed if it's in a fragment
          Ct(de),
          l,
          g,
          _
        ), S.el = se.el, j === null && no(l, se.el), A && re(A, g), (ne = S.props && S.props.onVnodeUpdated) && re(
          () => ge(ne, I, S, L),
          g
        );
      } else {
        let S;
        const { el: T, props: A } = c, { bm: I, m: L, parent: j, root: ne, type: se } = l, de = at(c);
        Ve(l, !1), I && Xt(I), !de && (S = A && A.onVnodeBeforeMount) && ge(S, j, c), Ve(l, !0);
        {
          ne.ce && ne.ce._injectChildStyle(se);
          const he = l.subTree = ks(l);
          M(
            null,
            he,
            d,
            m,
            l,
            g,
            _
          ), c.el = he.el;
        }
        if (L && re(L, g), !de && (S = A && A.onVnodeMounted)) {
          const he = c;
          re(
            () => ge(S, j, he),
            g
          );
        }
        (c.shapeFlag & 256 || j && at(j.vnode) && j.vnode.shapeFlag & 256) && l.a && re(l.a, g), l.isMounted = !0, c = d = m = null;
      }
    };
    l.scope.on();
    const y = l.effect = new On(x);
    l.scope.off();
    const b = l.update = y.run.bind(y), C = l.job = y.runIfDirty.bind(y);
    C.i = l, C.id = l.uid, y.scheduler = () => Ms(C), Ve(l, !0), b();
  }, B = (l, c, d) => {
    c.component = l;
    const m = l.vnode.props;
    l.vnode = c, l.next = null, Vr(l, c.props, m, d), Wr(l, c.children, d), De(), qs(l), je();
  }, N = (l, c, d, m, g, _, v, x, y = !1) => {
    const b = l && l.children, C = l ? l.shapeFlag : 0, S = c.children, { patchFlag: T, shapeFlag: A } = c;
    if (T > 0) {
      if (T & 128) {
        Tt(
          b,
          S,
          d,
          m,
          g,
          _,
          v,
          x,
          y
        );
        return;
      } else if (T & 256) {
        He(
          b,
          S,
          d,
          m,
          g,
          _,
          v,
          x,
          y
        );
        return;
      }
    }
    A & 8 ? (C & 16 && tt(b, g, _), S !== b && a(d, S)) : C & 16 ? A & 16 ? Tt(
      b,
      S,
      d,
      m,
      g,
      _,
      v,
      x,
      y
    ) : tt(b, g, _, !0) : (C & 8 && a(d, ""), A & 16 && Ae(
      S,
      d,
      m,
      g,
      _,
      v,
      x,
      y
    ));
  }, He = (l, c, d, m, g, _, v, x, y) => {
    l = l || Ye, c = c || Ye;
    const b = l.length, C = c.length, S = Math.min(b, C);
    let T;
    for (T = 0; T < S; T++) {
      const A = c[T] = y ? Re(c[T]) : me(c[T]);
      M(
        l[T],
        A,
        d,
        null,
        g,
        _,
        v,
        x,
        y
      );
    }
    b > C ? tt(
      l,
      g,
      _,
      !0,
      !1,
      S
    ) : Ae(
      c,
      d,
      m,
      g,
      _,
      v,
      x,
      y,
      S
    );
  }, Tt = (l, c, d, m, g, _, v, x, y) => {
    let b = 0;
    const C = c.length;
    let S = l.length - 1, T = C - 1;
    for (; b <= S && b <= T; ) {
      const A = l[b], I = c[b] = y ? Re(c[b]) : me(c[b]);
      if (rt(A, I))
        M(
          A,
          I,
          d,
          null,
          g,
          _,
          v,
          x,
          y
        );
      else
        break;
      b++;
    }
    for (; b <= S && b <= T; ) {
      const A = l[S], I = c[T] = y ? Re(c[T]) : me(c[T]);
      if (rt(A, I))
        M(
          A,
          I,
          d,
          null,
          g,
          _,
          v,
          x,
          y
        );
      else
        break;
      S--, T--;
    }
    if (b > S) {
      if (b <= T) {
        const A = T + 1, I = A < C ? c[A].el : m;
        for (; b <= T; )
          M(
            null,
            c[b] = y ? Re(c[b]) : me(c[b]),
            d,
            I,
            g,
            _,
            v,
            x,
            y
          ), b++;
      }
    } else if (b > T)
      for (; b <= S; )
        ae(l[b], g, _, !0), b++;
    else {
      const A = b, I = b, L = /* @__PURE__ */ new Map();
      for (b = I; b <= T; b++) {
        const ie = c[b] = y ? Re(c[b]) : me(c[b]);
        ie.key != null && L.set(ie.key, b);
      }
      let j, ne = 0;
      const se = T - I + 1;
      let de = !1, he = 0;
      const nt = new Array(se);
      for (b = 0; b < se; b++) nt[b] = 0;
      for (b = A; b <= S; b++) {
        const ie = l[b];
        if (ne >= se) {
          ae(ie, g, _, !0);
          continue;
        }
        let pe;
        if (ie.key != null)
          pe = L.get(ie.key);
        else
          for (j = I; j <= T; j++)
            if (nt[j - I] === 0 && rt(ie, c[j])) {
              pe = j;
              break;
            }
        pe === void 0 ? ae(ie, g, _, !0) : (nt[pe - I] = b + 1, pe >= he ? he = pe : de = !0, M(
          ie,
          c[pe],
          d,
          null,
          g,
          _,
          v,
          x,
          y
        ), ne++);
      }
      const Us = de ? Yr(nt) : Ye;
      for (j = Us.length - 1, b = se - 1; b >= 0; b--) {
        const ie = I + b, pe = c[ie], Bs = ie + 1 < C ? c[ie + 1].el : m;
        nt[b] === 0 ? M(
          null,
          pe,
          d,
          Bs,
          g,
          _,
          v,
          x,
          y
        ) : de && (j < 0 || b !== Us[j] ? Ne(pe, d, Bs, 2) : j--);
      }
    }
  }, Ne = (l, c, d, m, g = null) => {
    const { el: _, type: v, transition: x, children: y, shapeFlag: b } = l;
    if (b & 6) {
      Ne(l.component.subTree, c, d, m);
      return;
    }
    if (b & 128) {
      l.suspense.move(c, d, m);
      return;
    }
    if (b & 64) {
      v.move(l, c, d, st);
      return;
    }
    if (v === Ee) {
      n(_, c, d);
      for (let S = 0; S < y.length; S++)
        Ne(y[S], c, d, m);
      n(l.anchor, c, d);
      return;
    }
    if (v === is) {
      W(l, c, d);
      return;
    }
    if (m !== 2 && b & 1 && x)
      if (m === 0)
        x.beforeEnter(_), n(_, c, d), re(() => x.enter(_), g);
      else {
        const { leave: S, delayLeave: T, afterLeave: A } = x, I = () => n(_, c, d), L = () => {
          S(_, () => {
            I(), A && A();
          });
        };
        T ? T(_, I, L) : L();
      }
    else
      n(_, c, d);
  }, ae = (l, c, d, m = !1, g = !1) => {
    const {
      type: _,
      props: v,
      ref: x,
      children: y,
      dynamicChildren: b,
      shapeFlag: C,
      patchFlag: S,
      dirs: T,
      cacheIndex: A
    } = l;
    if (S === -2 && (g = !1), x != null && $t(x, null, d, l, !0), A != null && (c.renderCache[A] = void 0), C & 256) {
      c.ctx.deactivate(l);
      return;
    }
    const I = C & 1 && T, L = !at(l);
    let j;
    if (L && (j = v && v.onVnodeBeforeUnmount) && ge(j, c, l), C & 6)
      wi(l.component, d, m);
    else {
      if (C & 128) {
        l.suspense.unmount(d, m);
        return;
      }
      I && Le(l, null, c, "beforeUnmount"), C & 64 ? l.type.remove(
        l,
        c,
        d,
        st,
        m
      ) : b && // #5154
      // when v-once is used inside a block, setBlockTracking(-1) marks the
      // parent block with hasOnce: true
      // so that it doesn't take the fast path during unmount - otherwise
      // components nested in v-once are never unmounted.
      !b.hasOnce && // #1153: fast path should not be taken for non-stable (v-for) fragments
      (_ !== Ee || S > 0 && S & 64) ? tt(
        b,
        c,
        d,
        !1,
        !0
      ) : (_ === Ee && S & 384 || !g && C & 16) && tt(y, c, d), m && Ls(l);
    }
    (L && (j = v && v.onVnodeUnmounted) || I) && re(() => {
      j && ge(j, c, l), I && Le(l, null, c, "unmounted");
    }, d);
  }, Ls = (l) => {
    const { type: c, el: d, anchor: m, transition: g } = l;
    if (c === Ee) {
      Si(d, m);
      return;
    }
    if (c === is) {
      O(l);
      return;
    }
    const _ = () => {
      i(d), g && !g.persisted && g.afterLeave && g.afterLeave();
    };
    if (l.shapeFlag & 1 && g && !g.persisted) {
      const { leave: v, delayLeave: x } = g, y = () => v(d, _);
      x ? x(l.el, _, y) : y();
    } else
      _();
  }, Si = (l, c) => {
    let d;
    for (; l !== c; )
      d = w(l), i(l), l = d;
    i(c);
  }, wi = (l, c, d) => {
    const { bum: m, scope: g, job: _, subTree: v, um: x, m: y, a: b } = l;
    Qs(y), Qs(b), m && Xt(m), g.stop(), _ && (_.flags |= 8, ae(v, l, c, d)), x && re(x, c), re(() => {
      l.isUnmounted = !0;
    }, c), c && c.pendingBranch && !c.isUnmounted && l.asyncDep && !l.asyncResolved && l.suspenseId === c.pendingId && (c.deps--, c.deps === 0 && c.resolve());
  }, tt = (l, c, d, m = !1, g = !1, _ = 0) => {
    for (let v = _; v < l.length; v++)
      ae(l[v], c, d, m, g);
  }, Ct = (l) => {
    if (l.shapeFlag & 6)
      return Ct(l.component.subTree);
    if (l.shapeFlag & 128)
      return l.suspense.next();
    const c = w(l.anchor || l.el), d = c && c[gr];
    return d ? w(d) : c;
  };
  let Yt = !1;
  const Vs = (l, c, d) => {
    l == null ? c._vnode && ae(c._vnode, null, null, !0) : M(
      c._vnode || null,
      l,
      c,
      null,
      null,
      null,
      d
    ), c._vnode = l, Yt || (Yt = !0, qs(), qn(), Yt = !1);
  }, st = {
    p: M,
    um: ae,
    m: Ne,
    r: Ls,
    mt: Gt,
    mc: Ae,
    pc: N,
    pbc: $e,
    n: Ct,
    o: e
  };
  return {
    render: Vs,
    hydrate: void 0,
    createApp: Hr(Vs)
  };
}
function ss({ type: e, props: t }, s) {
  return s === "svg" && e === "foreignObject" || s === "mathml" && e === "annotation-xml" && t && t.encoding && t.encoding.includes("html") ? void 0 : s;
}
function Ve({ effect: e, job: t }, s) {
  s ? (e.flags |= 32, t.flags |= 4) : (e.flags &= -33, t.flags &= -5);
}
function Gr(e, t) {
  return (!e || e && !e.pendingBranch) && t && !t.persisted;
}
function ai(e, t, s = !1) {
  const n = e.children, i = t.children;
  if (P(n) && P(i))
    for (let r = 0; r < n.length; r++) {
      const o = n[r];
      let f = i[r];
      f.shapeFlag & 1 && !f.dynamicChildren && ((f.patchFlag <= 0 || f.patchFlag === 32) && (f = i[r] = Re(i[r]), f.el = o.el), !s && f.patchFlag !== -2 && ai(o, f)), f.type === qt && (f.el = o.el);
    }
}
function Yr(e) {
  const t = e.slice(), s = [0];
  let n, i, r, o, f;
  const u = e.length;
  for (n = 0; n < u; n++) {
    const h = e[n];
    if (h !== 0) {
      if (i = s[s.length - 1], e[i] < h) {
        t[n] = i, s.push(n);
        continue;
      }
      for (r = 0, o = s.length - 1; r < o; )
        f = r + o >> 1, e[s[f]] < h ? r = f + 1 : o = f;
      h < e[s[r]] && (r > 0 && (t[n] = s[r - 1]), s[r] = n);
    }
  }
  for (r = s.length, o = s[r - 1]; r-- > 0; )
    s[r] = o, o = t[o];
  return s;
}
function di(e) {
  const t = e.subTree.component;
  if (t)
    return t.asyncDep && !t.asyncResolved ? t : di(t);
}
function Qs(e) {
  if (e)
    for (let t = 0; t < e.length; t++)
      e[t].flags |= 8;
}
const zr = Symbol.for("v-scx"), Xr = () => Rt(zr);
function ns(e, t, s) {
  return hi(e, t, s);
}
function hi(e, t, s = U) {
  const { immediate: n, deep: i, flush: r, once: o } = s, f = te({}, s), u = t && n || !t && r !== "post";
  let h;
  if (yt) {
    if (r === "sync") {
      const E = Xr();
      h = E.__watcherHandles || (E.__watcherHandles = []);
    } else if (!u) {
      const E = () => {
      };
      return E.stop = ye, E.resume = ye, E.pause = ye, E;
    }
  }
  const a = k;
  f.call = (E, F, M) => ve(E, a, F, M);
  let p = !1;
  r === "post" ? f.scheduler = (E) => {
    re(E, a && a.suspense);
  } : r !== "sync" && (p = !0, f.scheduler = (E, F) => {
    F ? E() : Ms(E);
  }), f.augmentJob = (E) => {
    t && (E.flags |= 4), p && (E.flags |= 2, a && (E.id = a.uid, E.i = a));
  };
  const w = cr(e, t, f);
  return yt && (h ? h.push(w) : u && w()), w;
}
function Zr(e, t, s) {
  const n = this.proxy, i = G(e) ? e.includes(".") ? pi(n, e) : () => n[e] : e.bind(n, n);
  let r;
  R(t) ? r = t : (r = t.handler, s = t);
  const o = vt(this), f = hi(i, r.bind(n), s);
  return o(), f;
}
function pi(e, t) {
  const s = t.split(".");
  return () => {
    let n = e;
    for (let i = 0; i < s.length && n; i++)
      n = n[s[i]];
    return n;
  };
}
const Qr = (e, t) => t === "modelValue" || t === "model-value" ? e.modelModifiers : e[`${t}Modifiers`] || e[`${Me(t)}Modifiers`] || e[`${Je(t)}Modifiers`];
function kr(e, t, ...s) {
  if (e.isUnmounted) return;
  const n = e.vnode.props || U;
  let i = s;
  const r = t.startsWith("update:"), o = r && Qr(n, t.slice(7));
  o && (o.trim && (i = s.map((a) => G(a) ? a.trim() : a)), o.number && (i = s.map(Pi)));
  let f, u = n[f = zt(t)] || // also try camelCase event handler (#2249)
  n[f = zt(Me(t))];
  !u && r && (u = n[f = zt(Je(t))]), u && ve(
    u,
    e,
    6,
    i
  );
  const h = n[f + "Once"];
  if (h) {
    if (!e.emitted)
      e.emitted = {};
    else if (e.emitted[f])
      return;
    e.emitted[f] = !0, ve(
      h,
      e,
      6,
      i
    );
  }
}
function gi(e, t, s = !1) {
  const n = t.emitsCache, i = n.get(e);
  if (i !== void 0)
    return i;
  const r = e.emits;
  let o = {}, f = !1;
  if (!R(e)) {
    const u = (h) => {
      const a = gi(h, t, !0);
      a && (f = !0, te(o, a));
    };
    !s && t.mixins.length && t.mixins.forEach(u), e.extends && u(e.extends), e.mixins && e.mixins.forEach(u);
  }
  return !r && !f ? (J(e) && n.set(e, null), null) : (P(r) ? r.forEach((u) => o[u] = null) : te(o, r), J(e) && n.set(e, o), o);
}
function Jt(e, t) {
  return !e || !Lt(t) ? !1 : (t = t.slice(2).replace(/Once$/, ""), D(e, t[0].toLowerCase() + t.slice(1)) || D(e, Je(t)) || D(e, t));
}
function ks(e) {
  const {
    type: t,
    vnode: s,
    proxy: n,
    withProxy: i,
    propsOptions: [r],
    slots: o,
    attrs: f,
    emit: u,
    render: h,
    renderCache: a,
    props: p,
    data: w,
    setupState: E,
    ctx: F,
    inheritAttrs: M
  } = e, Y = jt(e);
  let H, K;
  try {
    if (s.shapeFlag & 4) {
      const O = i || n, q = O;
      H = me(
        h.call(
          q,
          O,
          a,
          p,
          E,
          w,
          F
        )
      ), K = f;
    } else {
      const O = t;
      H = me(
        O.length > 1 ? O(
          p,
          { attrs: f, slots: o, emit: u }
        ) : O(
          p,
          null
        )
      ), K = t.props ? f : eo(f);
    }
  } catch (O) {
    ht.length = 0, Kt(O, e, 1), H = We(mt);
  }
  let W = H;
  if (K && M !== !1) {
    const O = Object.keys(K), { shapeFlag: q } = W;
    O.length && q & 7 && (r && O.some(ys) && (K = to(
      K,
      r
    )), W = ke(W, K, !1, !0));
  }
  return s.dirs && (W = ke(W, null, !1, !0), W.dirs = W.dirs ? W.dirs.concat(s.dirs) : s.dirs), s.transition && Fs(W, s.transition), H = W, jt(Y), H;
}
const eo = (e) => {
  let t;
  for (const s in e)
    (s === "class" || s === "style" || Lt(s)) && ((t || (t = {}))[s] = e[s]);
  return t;
}, to = (e, t) => {
  const s = {};
  for (const n in e)
    (!ys(n) || !(n.slice(9) in t)) && (s[n] = e[n]);
  return s;
};
function so(e, t, s) {
  const { props: n, children: i, component: r } = e, { props: o, children: f, patchFlag: u } = t, h = r.emitsOptions;
  if (t.dirs || t.transition)
    return !0;
  if (s && u >= 0) {
    if (u & 1024)
      return !0;
    if (u & 16)
      return n ? en(n, o, h) : !!o;
    if (u & 8) {
      const a = t.dynamicProps;
      for (let p = 0; p < a.length; p++) {
        const w = a[p];
        if (o[w] !== n[w] && !Jt(h, w))
          return !0;
      }
    }
  } else
    return (i || f) && (!f || !f.$stable) ? !0 : n === o ? !1 : n ? o ? en(n, o, h) : !0 : !!o;
  return !1;
}
function en(e, t, s) {
  const n = Object.keys(t);
  if (n.length !== Object.keys(e).length)
    return !0;
  for (let i = 0; i < n.length; i++) {
    const r = n[i];
    if (t[r] !== e[r] && !Jt(s, r))
      return !0;
  }
  return !1;
}
function no({ vnode: e, parent: t }, s) {
  for (; t; ) {
    const n = t.subTree;
    if (n.suspense && n.suspense.activeBranch === e && (n.el = e.el), n === e)
      (e = t.vnode).el = s, t = t.parent;
    else
      break;
  }
}
const _i = (e) => e.__isSuspense;
function io(e, t) {
  t && t.pendingBranch ? P(e) ? t.effects.push(...e) : t.effects.push(e) : hr(e);
}
const Ee = Symbol.for("v-fgt"), qt = Symbol.for("v-txt"), mt = Symbol.for("v-cmt"), is = Symbol.for("v-stc"), ht = [];
let fe = null;
function ro(e = !1) {
  ht.push(fe = e ? null : []);
}
function oo() {
  ht.pop(), fe = ht[ht.length - 1] || null;
}
let bt = 1;
function tn(e, t = !1) {
  bt += e, e < 0 && fe && t && (fe.hasOnce = !0);
}
function lo(e) {
  return e.dynamicChildren = bt > 0 ? fe || Ye : null, oo(), bt > 0 && fe && fe.push(e), e;
}
function fo(e, t, s, n, i, r) {
  return lo(
    js(
      e,
      t,
      s,
      n,
      i,
      r,
      !0
    )
  );
}
function mi(e) {
  return e ? e.__v_isVNode === !0 : !1;
}
function rt(e, t) {
  return e.type === t.type && e.key === t.key;
}
const bi = ({ key: e }) => e ?? null, It = ({
  ref: e,
  ref_key: t,
  ref_for: s
}) => (typeof e == "number" && (e = "" + e), e != null ? G(e) || ee(e) || R(e) ? { i: be, r: e, k: t, f: !!s } : e : null);
function js(e, t = null, s = null, n = 0, i = null, r = e === Ee ? 0 : 1, o = !1, f = !1) {
  const u = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e,
    props: t,
    key: t && bi(t),
    ref: t && It(t),
    scopeId: Yn,
    slotScopeIds: null,
    children: s,
    component: null,
    suspense: null,
    ssContent: null,
    ssFallback: null,
    dirs: null,
    transition: null,
    el: null,
    anchor: null,
    target: null,
    targetStart: null,
    targetAnchor: null,
    staticCount: 0,
    shapeFlag: r,
    patchFlag: n,
    dynamicProps: i,
    dynamicChildren: null,
    appContext: null,
    ctx: be
  };
  return f ? ($s(u, s), r & 128 && e.normalize(u)) : s && (u.shapeFlag |= G(s) ? 8 : 16), bt > 0 && // avoid a block node from tracking itself
  !o && // has current parent block
  fe && // presence of a patch flag indicates this node needs patching on updates.
  // component nodes also should always be patched, because even if the
  // component doesn't need to update, it needs to persist the instance on to
  // the next vnode so that it can be properly unmounted later.
  (u.patchFlag > 0 || r & 6) && // the EVENTS flag is only for hydration and if it is the only flag, the
  // vnode should not be considered dynamic due to handler caching.
  u.patchFlag !== 32 && fe.push(u), u;
}
const We = co;
function co(e, t = null, s = null, n = 0, i = null, r = !1) {
  if ((!e || e === Pr) && (e = mt), mi(e)) {
    const f = ke(
      e,
      t,
      !0
      /* mergeRef: true */
    );
    return s && $s(f, s), bt > 0 && !r && fe && (f.shapeFlag & 6 ? fe[fe.indexOf(e)] = f : fe.push(f)), f.patchFlag = -2, f;
  }
  if (vo(e) && (e = e.__vccOpts), t) {
    t = uo(t);
    let { class: f, style: u } = t;
    f && !G(f) && (t.class = ws(f)), J(u) && (Is(u) && !P(u) && (u = te({}, u)), t.style = Ss(u));
  }
  const o = G(e) ? 1 : _i(e) ? 128 : _r(e) ? 64 : J(e) ? 4 : R(e) ? 2 : 0;
  return js(
    e,
    t,
    s,
    n,
    i,
    o,
    r,
    !0
  );
}
function uo(e) {
  return e ? Is(e) || ii(e) ? te({}, e) : e : null;
}
function ke(e, t, s = !1, n = !1) {
  const { props: i, ref: r, patchFlag: o, children: f, transition: u } = e, h = t ? ho(i || {}, t) : i, a = {
    __v_isVNode: !0,
    __v_skip: !0,
    type: e.type,
    props: h,
    key: h && bi(h),
    ref: t && t.ref ? (
      // #2078 in the case of <component :is="vnode" ref="extra"/>
      // if the vnode itself already has a ref, cloneVNode will need to merge
      // the refs so the single vnode can be set on multiple refs
      s && r ? P(r) ? r.concat(It(t)) : [r, It(t)] : It(t)
    ) : r,
    scopeId: e.scopeId,
    slotScopeIds: e.slotScopeIds,
    children: f,
    target: e.target,
    targetStart: e.targetStart,
    targetAnchor: e.targetAnchor,
    staticCount: e.staticCount,
    shapeFlag: e.shapeFlag,
    // if the vnode is cloned with extra props, we can no longer assume its
    // existing patch flag to be reliable and need to add the FULL_PROPS flag.
    // note: preserve flag for fragments since they use the flag for children
    // fast paths only.
    patchFlag: t && e.type !== Ee ? o === -1 ? 16 : o | 16 : o,
    dynamicProps: e.dynamicProps,
    dynamicChildren: e.dynamicChildren,
    appContext: e.appContext,
    dirs: e.dirs,
    transition: u,
    // These should technically only be non-null on mounted VNodes. However,
    // they *should* be copied for kept-alive vnodes. So we just always copy
    // them since them being non-null during a mount doesn't affect the logic as
    // they will simply be overwritten.
    component: e.component,
    suspense: e.suspense,
    ssContent: e.ssContent && ke(e.ssContent),
    ssFallback: e.ssFallback && ke(e.ssFallback),
    el: e.el,
    anchor: e.anchor,
    ctx: e.ctx,
    ce: e.ce
  };
  return u && n && Fs(
    a,
    u.clone(a)
  ), a;
}
function ao(e = " ", t = 0) {
  return We(qt, null, e, t);
}
function me(e) {
  return e == null || typeof e == "boolean" ? We(mt) : P(e) ? We(
    Ee,
    null,
    // #3666, avoid reference pollution when reusing vnode
    e.slice()
  ) : mi(e) ? Re(e) : We(qt, null, String(e));
}
function Re(e) {
  return e.el === null && e.patchFlag !== -1 || e.memo ? e : ke(e);
}
function $s(e, t) {
  let s = 0;
  const { shapeFlag: n } = e;
  if (t == null)
    t = null;
  else if (P(t))
    s = 16;
  else if (typeof t == "object")
    if (n & 65) {
      const i = t.default;
      i && (i._c && (i._d = !1), $s(e, i()), i._c && (i._d = !0));
      return;
    } else {
      s = 32;
      const i = t._;
      !i && !ii(t) ? t._ctx = be : i === 3 && be && (be.slots._ === 1 ? t._ = 1 : (t._ = 2, e.patchFlag |= 1024));
    }
  else R(t) ? (t = { default: t, _ctx: be }, s = 32) : (t = String(t), n & 64 ? (s = 16, t = [ao(t)]) : s = 8);
  e.children = t, e.shapeFlag |= s;
}
function ho(...e) {
  const t = {};
  for (let s = 0; s < e.length; s++) {
    const n = e[s];
    for (const i in n)
      if (i === "class")
        t.class !== n.class && (t.class = ws([t.class, n.class]));
      else if (i === "style")
        t.style = Ss([t.style, n.style]);
      else if (Lt(i)) {
        const r = t[i], o = n[i];
        o && r !== o && !(P(r) && r.includes(o)) && (t[i] = r ? [].concat(r, o) : o);
      } else i !== "" && (t[i] = n[i]);
  }
  return t;
}
function ge(e, t, s, n = null) {
  ve(e, t, 7, [
    s,
    n
  ]);
}
const po = ti();
let go = 0;
function _o(e, t, s) {
  const n = e.type, i = (t ? t.appContext : e.appContext) || po, r = {
    uid: go++,
    vnode: e,
    type: n,
    parent: t,
    appContext: i,
    root: null,
    // to be immediately set
    next: null,
    subTree: null,
    // will be set synchronously right after creation
    effect: null,
    update: null,
    // will be set synchronously right after creation
    job: null,
    scope: new $i(
      !0
      /* detached */
    ),
    render: null,
    proxy: null,
    exposed: null,
    exposeProxy: null,
    withProxy: null,
    provides: t ? t.provides : Object.create(i.provides),
    ids: t ? t.ids : ["", 0, 0],
    accessCache: null,
    renderCache: [],
    // local resolved assets
    components: null,
    directives: null,
    // resolved props and emits options
    propsOptions: oi(n, i),
    emitsOptions: gi(n, i),
    // emit
    emit: null,
    // to be set immediately
    emitted: null,
    // props default value
    propsDefaults: U,
    // inheritAttrs
    inheritAttrs: n.inheritAttrs,
    // state
    ctx: U,
    data: U,
    props: U,
    attrs: U,
    slots: U,
    refs: U,
    setupState: U,
    setupContext: null,
    // suspense related
    suspense: s,
    suspenseId: s ? s.pendingId : 0,
    asyncDep: null,
    asyncResolved: !1,
    // lifecycle hooks
    // not using enums here because it results in computed properties
    isMounted: !1,
    isUnmounted: !1,
    isDeactivated: !1,
    bc: null,
    c: null,
    bm: null,
    m: null,
    bu: null,
    u: null,
    um: null,
    bum: null,
    da: null,
    a: null,
    rtg: null,
    rtc: null,
    ec: null,
    sp: null
  };
  return r.ctx = { _: r }, r.root = t ? t.root : r, r.emit = kr.bind(null, r), e.ce && e.ce(r), r;
}
let k = null, Nt, _s;
{
  const e = Bt(), t = (s, n) => {
    let i;
    return (i = e[s]) || (i = e[s] = []), i.push(n), (r) => {
      i.length > 1 ? i.forEach((o) => o(r)) : i[0](r);
    };
  };
  Nt = t(
    "__VUE_INSTANCE_SETTERS__",
    (s) => k = s
  ), _s = t(
    "__VUE_SSR_SETTERS__",
    (s) => yt = s
  );
}
const vt = (e) => {
  const t = k;
  return Nt(e), e.scope.on(), () => {
    e.scope.off(), Nt(t);
  };
}, sn = () => {
  k && k.scope.off(), Nt(null);
};
function yi(e) {
  return e.vnode.shapeFlag & 4;
}
let yt = !1;
function mo(e, t = !1, s = !1) {
  t && _s(t);
  const { props: n, children: i } = e.vnode, r = yi(e);
  Lr(e, n, r, t), Kr(e, i, s);
  const o = r ? bo(e, t) : void 0;
  return t && _s(!1), o;
}
function bo(e, t) {
  const s = e.type;
  e.accessCache = /* @__PURE__ */ Object.create(null), e.proxy = new Proxy(e.ctx, Rr);
  const { setup: n } = s;
  if (n) {
    De();
    const i = e.setupContext = n.length > 1 ? xo(e) : null, r = vt(e), o = xt(
      n,
      e,
      0,
      [
        e.props,
        i
      ]
    ), f = bn(o);
    if (je(), r(), (f || e.sp) && !at(e) && zn(e), f) {
      if (o.then(sn, sn), t)
        return o.then((u) => {
          nn(e, u);
        }).catch((u) => {
          Kt(u, e, 0);
        });
      e.asyncDep = o;
    } else
      nn(e, o);
  } else
    xi(e);
}
function nn(e, t, s) {
  R(t) ? e.type.__ssrInlineRender ? e.ssrRender = t : e.render = t : J(t) && (e.setupState = Kn(t)), xi(e);
}
function xi(e, t, s) {
  const n = e.type;
  e.render || (e.render = n.render || ye);
  {
    const i = vt(e);
    De();
    try {
      Ir(e);
    } finally {
      je(), i();
    }
  }
}
const yo = {
  get(e, t) {
    return z(e, "get", ""), e[t];
  }
};
function xo(e) {
  const t = (s) => {
    e.exposed = s || {};
  };
  return {
    attrs: new Proxy(e.attrs, yo),
    slots: e.slots,
    emit: e.emit,
    expose: t
  };
}
function Hs(e) {
  return e.exposed ? e.exposeProxy || (e.exposeProxy = new Proxy(Kn(nr(e.exposed)), {
    get(t, s) {
      if (s in t)
        return t[s];
      if (s in dt)
        return dt[s](e);
    },
    has(t, s) {
      return s in t || s in dt;
    }
  })) : e.proxy;
}
function vo(e) {
  return R(e) && "__vccOpts" in e;
}
const So = (e, t) => lr(e, t, yt), wo = "3.5.13";
/**
* @vue/runtime-dom v3.5.13
* (c) 2018-present Yuxi (Evan) You and Vue contributors
* @license MIT
**/
let ms;
const rn = typeof window < "u" && window.trustedTypes;
if (rn)
  try {
    ms = /* @__PURE__ */ rn.createPolicy("vue", {
      createHTML: (e) => e
    });
  } catch {
  }
const vi = ms ? (e) => ms.createHTML(e) : (e) => e, Eo = "http://www.w3.org/2000/svg", To = "http://www.w3.org/1998/Math/MathML", we = typeof document < "u" ? document : null, on = we && /* @__PURE__ */ we.createElement("template"), Co = {
  insert: (e, t, s) => {
    t.insertBefore(e, s || null);
  },
  remove: (e) => {
    const t = e.parentNode;
    t && t.removeChild(e);
  },
  createElement: (e, t, s, n) => {
    const i = t === "svg" ? we.createElementNS(Eo, e) : t === "mathml" ? we.createElementNS(To, e) : s ? we.createElement(e, { is: s }) : we.createElement(e);
    return e === "select" && n && n.multiple != null && i.setAttribute("multiple", n.multiple), i;
  },
  createText: (e) => we.createTextNode(e),
  createComment: (e) => we.createComment(e),
  setText: (e, t) => {
    e.nodeValue = t;
  },
  setElementText: (e, t) => {
    e.textContent = t;
  },
  parentNode: (e) => e.parentNode,
  nextSibling: (e) => e.nextSibling,
  querySelector: (e) => we.querySelector(e),
  setScopeId(e, t) {
    e.setAttribute(t, "");
  },
  // __UNSAFE__
  // Reason: innerHTML.
  // Static content here can only come from compiled templates.
  // As long as the user only uses trusted templates, this is safe.
  insertStaticContent(e, t, s, n, i, r) {
    const o = s ? s.previousSibling : t.lastChild;
    if (i && (i === r || i.nextSibling))
      for (; t.insertBefore(i.cloneNode(!0), s), !(i === r || !(i = i.nextSibling)); )
        ;
    else {
      on.innerHTML = vi(
        n === "svg" ? `<svg>${e}</svg>` : n === "mathml" ? `<math>${e}</math>` : e
      );
      const f = on.content;
      if (n === "svg" || n === "mathml") {
        const u = f.firstChild;
        for (; u.firstChild; )
          f.appendChild(u.firstChild);
        f.removeChild(u);
      }
      t.insertBefore(f, s);
    }
    return [
      // first
      o ? o.nextSibling : t.firstChild,
      // last
      s ? s.previousSibling : t.lastChild
    ];
  }
}, Oo = Symbol("_vtc");
function Ao(e, t, s) {
  const n = e[Oo];
  n && (t = (t ? [t, ...n] : [...n]).join(" ")), t == null ? e.removeAttribute("class") : s ? e.setAttribute("class", t) : e.className = t;
}
const ln = Symbol("_vod"), Po = Symbol("_vsh"), Ro = Symbol(""), Io = /(^|;)\s*display\s*:/;
function Mo(e, t, s) {
  const n = e.style, i = G(s);
  let r = !1;
  if (s && !i) {
    if (t)
      if (G(t))
        for (const o of t.split(";")) {
          const f = o.slice(0, o.indexOf(":")).trim();
          s[f] == null && Mt(n, f, "");
        }
      else
        for (const o in t)
          s[o] == null && Mt(n, o, "");
    for (const o in s)
      o === "display" && (r = !0), Mt(n, o, s[o]);
  } else if (i) {
    if (t !== s) {
      const o = n[Ro];
      o && (s += ";" + o), n.cssText = s, r = Io.test(s);
    }
  } else t && e.removeAttribute("style");
  ln in e && (e[ln] = r ? n.display : "", e[Po] && (n.display = "none"));
}
const fn = /\s*!important$/;
function Mt(e, t, s) {
  if (P(s))
    s.forEach((n) => Mt(e, t, n));
  else if (s == null && (s = ""), t.startsWith("--"))
    e.setProperty(t, s);
  else {
    const n = Fo(e, t);
    fn.test(s) ? e.setProperty(
      Je(n),
      s.replace(fn, ""),
      "important"
    ) : e[n] = s;
  }
}
const cn = ["Webkit", "Moz", "ms"], rs = {};
function Fo(e, t) {
  const s = rs[t];
  if (s)
    return s;
  let n = Me(t);
  if (n !== "filter" && n in e)
    return rs[t] = n;
  n = vn(n);
  for (let i = 0; i < cn.length; i++) {
    const r = cn[i] + n;
    if (r in e)
      return rs[t] = r;
  }
  return t;
}
const un = "http://www.w3.org/1999/xlink";
function an(e, t, s, n, i, r = ji(t)) {
  n && t.startsWith("xlink:") ? s == null ? e.removeAttributeNS(un, t.slice(6, t.length)) : e.setAttributeNS(un, t, s) : s == null || r && !wn(s) ? e.removeAttribute(t) : e.setAttribute(
    t,
    r ? "" : Fe(s) ? String(s) : s
  );
}
function dn(e, t, s, n, i) {
  if (t === "innerHTML" || t === "textContent") {
    s != null && (e[t] = t === "innerHTML" ? vi(s) : s);
    return;
  }
  const r = e.tagName;
  if (t === "value" && r !== "PROGRESS" && // custom elements may use _value internally
  !r.includes("-")) {
    const f = r === "OPTION" ? e.getAttribute("value") || "" : e.value, u = s == null ? (
      // #11647: value should be set as empty string for null and undefined,
      // but <input type="checkbox"> should be set as 'on'.
      e.type === "checkbox" ? "on" : ""
    ) : String(s);
    (f !== u || !("_value" in e)) && (e.value = u), s == null && e.removeAttribute(t), e._value = s;
    return;
  }
  let o = !1;
  if (s === "" || s == null) {
    const f = typeof e[t];
    f === "boolean" ? s = wn(s) : s == null && f === "string" ? (s = "", o = !0) : f === "number" && (s = 0, o = !0);
  }
  try {
    e[t] = s;
  } catch {
  }
  o && e.removeAttribute(i || t);
}
function Do(e, t, s, n) {
  e.addEventListener(t, s, n);
}
function jo(e, t, s, n) {
  e.removeEventListener(t, s, n);
}
const hn = Symbol("_vei");
function $o(e, t, s, n, i = null) {
  const r = e[hn] || (e[hn] = {}), o = r[t];
  if (n && o)
    o.value = n;
  else {
    const [f, u] = Ho(t);
    if (n) {
      const h = r[t] = Vo(
        n,
        i
      );
      Do(e, f, h, u);
    } else o && (jo(e, f, o, u), r[t] = void 0);
  }
}
const pn = /(?:Once|Passive|Capture)$/;
function Ho(e) {
  let t;
  if (pn.test(e)) {
    t = {};
    let n;
    for (; n = e.match(pn); )
      e = e.slice(0, e.length - n[0].length), t[n[0].toLowerCase()] = !0;
  }
  return [e[2] === ":" ? e.slice(3) : Je(e.slice(2)), t];
}
let os = 0;
const No = /* @__PURE__ */ Promise.resolve(), Lo = () => os || (No.then(() => os = 0), os = Date.now());
function Vo(e, t) {
  const s = (n) => {
    if (!n._vts)
      n._vts = Date.now();
    else if (n._vts <= s.attached)
      return;
    ve(
      Uo(n, s.value),
      t,
      5,
      [n]
    );
  };
  return s.value = e, s.attached = Lo(), s;
}
function Uo(e, t) {
  if (P(t)) {
    const s = e.stopImmediatePropagation;
    return e.stopImmediatePropagation = () => {
      s.call(e), e._stopped = !0;
    }, t.map(
      (n) => (i) => !i._stopped && n && n(i)
    );
  } else
    return t;
}
const gn = (e) => e.charCodeAt(0) === 111 && e.charCodeAt(1) === 110 && // lowercase letter
e.charCodeAt(2) > 96 && e.charCodeAt(2) < 123, Bo = (e, t, s, n, i, r) => {
  const o = i === "svg";
  t === "class" ? Ao(e, n, o) : t === "style" ? Mo(e, s, n) : Lt(t) ? ys(t) || $o(e, t, s, n, r) : (t[0] === "." ? (t = t.slice(1), !0) : t[0] === "^" ? (t = t.slice(1), !1) : Ko(e, t, n, o)) ? (dn(e, t, n), !e.tagName.includes("-") && (t === "value" || t === "checked" || t === "selected") && an(e, t, n, o, r, t !== "value")) : /* #11081 force set props for possible async custom element */ e._isVueCE && (/[A-Z]/.test(t) || !G(n)) ? dn(e, Me(t), n, r, t) : (t === "true-value" ? e._trueValue = n : t === "false-value" && (e._falseValue = n), an(e, t, n, o));
};
function Ko(e, t, s, n) {
  if (n)
    return !!(t === "innerHTML" || t === "textContent" || t in e && gn(t) && R(s));
  if (t === "spellcheck" || t === "draggable" || t === "translate" || t === "form" || t === "list" && e.tagName === "INPUT" || t === "type" && e.tagName === "TEXTAREA")
    return !1;
  if (t === "width" || t === "height") {
    const i = e.tagName;
    if (i === "IMG" || i === "VIDEO" || i === "CANVAS" || i === "SOURCE")
      return !1;
  }
  return gn(t) && G(s) ? !1 : t in e;
}
const Wo = /* @__PURE__ */ te({ patchProp: Bo }, Co);
let _n;
function Jo() {
  return _n || (_n = Jr(Wo));
}
const qo = (...e) => {
  const t = Jo().createApp(...e), { mount: s } = t;
  return t.mount = (n) => {
    const i = Yo(n);
    if (!i) return;
    const r = t._component;
    !R(r) && !r.render && !r.template && (r.template = i.innerHTML), i.nodeType === 1 && (i.textContent = "");
    const o = s(i, !1, Go(i));
    return i instanceof Element && (i.removeAttribute("v-cloak"), i.setAttribute("data-v-app", "")), o;
  }, t;
};
function Go(e) {
  if (e instanceof SVGElement)
    return "svg";
  if (typeof MathMLElement == "function" && e instanceof MathMLElement)
    return "mathml";
}
function Yo(e) {
  return G(e) ? document.querySelector(e) : e;
}
const zo = (e, t) => {
  const s = e.__vccOpts || e;
  for (const [n, i] of t)
    s[n] = i;
  return s;
}, Xo = {
  name: "dm-json-form3",
  components: {},
  props: {
    options: {
      type: Object
    },
    schema: {
      type: Object
    },
    data: {
      type: Object
    },
    enabled: {
      type: Boolean,
      default: !0
    },
    ready: {
      type: Boolean,
      default: !1
    },
    title: {
      type: String,
      default: ""
    }
  },
  methods: {
    init() {
      console.debug("init: ", this.$el), this.editor.on("ready", () => {
        console.debug("JSONEditor is ready"), this.$emit("ready", !0);
      }), this.editor.on("change", () => {
        let e = this.editor.getValue();
        e === "" && (e = null), this.$emit("change", e);
      });
    },
    setValue(e) {
      console.debug("setValue: ", e), this.editor ? this.editor.setValue(e) : console.warn("Editor not initialized yet, skipping data update");
    },
    setOptions(e) {
      console.debug("setOptions: ", e), this.editor && this.editor.destroy(), this._options = { ...this._options, ...e }, this.editor = new JSONEditor(this.$el, this._options), this.$emit("ready", !1), this.init();
    },
    setSchema(e) {
      console.debug("setSchema: ", e);
      var t = null;
      this.editor && (t = this.editor.getValue(), this.editor.destroy()), this._options = { ...this._options, schema: e, startval: t }, this.editor = new JSONEditor(this.$el, this._options), this.$emit("ready", !1), this.init();
    }
  },
  async mounted() {
    await import("https://esm.sh/@json-editor/json-editor@latest"), this._options = { theme: "bootstrap4", iconlib: "spectre", remove_button_labels: !0, ajax: !0, ajax_cache_responses: !1, disable_collapse: !1, disable_edit_json: !0, disable_properties: !1, use_default_values: !0, required_by_default: !1, display_required_only: !0, show_opt_in: !1, show_errors: "always", disable_array_reorder: !1, disable_array_delete_all_rows: !1, disable_array_delete_last_row: !1, keep_oneof_values: !1, no_additional_properties: !0, case_sensitive_property_search: !1, ...this.options }, console.debug("Options: ", this._options), this.editor = new JSONEditor(this.$el, this._options), console.debug("Editor: ", this.editor), this.init();
  },
  emits: ["onChange", "onReady"]
}, Zo = {
  ref: "jsoneditor",
  id: "jsoneditor",
  class: "bootstrap-wrapper"
};
function Qo(e, t, s, n, i, r) {
  return ro(), fo("div", Zo, [
    js("h2", null, Tn(s.title), 1)
  ], 512);
}
const ko = /* @__PURE__ */ zo(Xo, [["render", Qo]]);
function tl({ model: e, el: t }) {
  const s = document.createElement("div");
  s.setAttribute("id", "jsoneditor-container"), t.append(s), console.debug("Create App");
  let n = e.get("options");
  n = n || {
    theme: "bootstrap4",
    iconlib: "spectre",
    schema: {
      title: "Editor Test",
      required: ["test"],
      properties: { test: { type: "string" } }
    }
    //   startval: this.data
  };
  const r = qo(ko, {
    options: n,
    onChange: (o) => {
      console.debug("CHANGE", o), o instanceof Event || (e.set("value", o), e.save_changes());
    },
    onReady: (o) => {
      console.debug("JSONEditor is ready"), e.set("ready", o), e.save_changes();
    }
  }).mount(t);
  e.on("change:value", () => {
    r.setValue(e.get("value"));
  }), e.on("change:options", () => {
    r.setOptions(e.get("options"));
  }), e.on("change:schema", () => {
    r.setSchema(e.get("schema"));
  });
}
export {
  tl as render
};
