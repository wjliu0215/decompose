import numpy as np
from numpy.random import uniform as rand, normal as randn, randint as randi
from numpy import sqrt, pi, exp, log, floor, array
from scipy.special import erf
import scipy as sp
import scipy.stats
import tensorflow as tf
from tefa.utils.tfppf import tfppf


def updateTensor(x, mask, newValues):
    if (x.dtype == tf.float32) or (x.dtype == tf.float64):
        indices = tf.cast(tf.where(mask), dtype=tf.int32)
        newValuesExpanded = tf.scatter_nd(indices,  newValues, tf.shape(x))
        updatedX = tf.where(mask, newValuesExpanded, x)
    else:
        indices = tf.cast(tf.where(mask), dtype=tf.int32)
        newValuesExpanded = tf.cast(tf.scatter_nd(indices,  tf.cast(newValues, dtype=tf.float32), tf.shape(x)), dtype=x.dtype)
        updatedX = tf.where(mask, newValuesExpanded, x)
    return(updatedX)


def randint(low, high):
    intervalLength = high-low
    r = tf.random_uniform(shape=tf.shape(low))
    r = tf.cast(tf.cast(intervalLength, dtype=r.dtype)*r, tf.int32)+low
    return(r)


def gather(data, indexes):
    if (data.dtype == tf.int32) or (data.dtype == tf.int64):
        return(tf.cast(tf.gather(tf.cast(data, dtype=tf.float32),
                                 indexes),
                       dtype=data.dtype))
    else:
        return(tf.gather(data, indexes))

def gather_nd(data, indexes):
    if (data.dtype == tf.int32) or (data.dtype == tf.int64):
        return(tf.cast(tf.gather_nd(tf.cast(data, dtype=tf.float32),
                                    indexes),
                       dtype=data.dtype))
    else:
        return(tf.gather_nd(data, indexes))

def count_nonzero(data, axis, keep_dims=False, dtype=tf.int32):
    # nNotValid = tf.count_nonzero(data, axis=-1, keep_dims=True)  # does not work on GPU!
    return(tf.reduce_sum(tf.cast(data, dtype=dtype),
                         axis=axis,
                         keep_dims=keep_dims))


def rejectionSamplingExp(a, b):
    dtype = a.dtype

    twoasq = 2*a**2
    expab = tf.exp(-a*(b-a)) - 1.

    z = tf.log(1 + tf.random_uniform(shape=tf.shape(a), dtype=dtype)*expab)
    e = -tf.log(tf.random_uniform(shape=tf.shape(a), dtype=dtype))

    def notStop(z, e):
        stop = tf.reduce_all((twoasq*e > z ** 2))
        notStop = tf.logical_not(stop)
        return(notStop)

    def body(z, e):
        notOk = tf.logical_not(twoasq*e > z ** 2)
        whereNotOk = tf.where(notOk)
        nNotOk = count_nonzero(notOk, dtype=tf.int32, axis=-1, keep_dims=True)

        u = tf.random_uniform(shape=nNotOk, dtype=dtype)
        expabNotOk = tf.gather(expab, whereNotOk)[..., 0]
        zUpdates = tf.log(1. + u*expabNotOk)
        z = updateTensor(z, notOk, zUpdates)

        u = tf.random_uniform(shape=nNotOk, dtype=dtype)
        eUpdates = -tf.log(u)
        e = updateTensor(e, notOk, eUpdates)
        return(z, e)

    z, e = tf.while_loop(notStop, body, loop_vars=[z, e])

    #r = a - z/a
    r = z
    return(r)

def rejectionSamplingNorm(a, b):
    dtype = a.dtype

    r = tf.random_normal(shape=tf.shape(a), dtype=dtype)

    def notStop(r):
        stop = tf.reduce_all((r>=a) & (r<=b))
        notStop = tf.logical_not(stop)
        return(notStop)

    def body(r):
        notOk = tf.logical_not((r>=a) & (r<=b))
        whereNotOk = tf.where(notOk)
        nNotOk = count_nonzero(notOk, dtype=tf.int32, axis=-1, keep_dims=True)

        n = tf.random_normal(shape=nNotOk, dtype=r.dtype)
        r = updateTensor(r, notOk, n)
        return(r)

    r = tf.while_loop(notStop, body, loop_vars=[r])
    return(r)
#    return(tf.abs(r))

def ppf(a, b):
    # use ppf method
    norm = tf.contrib.distributions.Normal(loc=tf.constant(0.,dtype=a.dtype),
                                           scale=tf.constant(1., dtype=a.dtype))
    f = norm.cdf(a)
    t = norm.cdf(b)
    u = tf.random_uniform(shape=tf.shape(a), dtype=a.dtype)*(t-f)+f
    r = tfppf(u)
    return r

def rightTail(a, b):
    xmin, xmax, kmin, INCH, I0, ALPHA, N, yl0, ylN, x, yu, ncell = getConsts(a.dtype)
    lbound = x[-1]
    z = -tf.log(tf.random_uniform(shape=tf.shape(a), dtype=a.dtype))
    e = -tf.log(tf.random_uniform(shape=tf.shape(a), dtype=a.dtype))
    z = z / lbound
    r = lbound + z
    accepted = tf.logical_and(tf.less_equal(z**2, 2*e),
                              tf.less(z, b-lbound))
    return(r, accepted)

def getConsts(dtype):
    xmin = tf.constant(-2.00443204036, dtype=dtype)
    xmax = tf.constant(3.48672170399, dtype=dtype)
    kmin = tf.constant(5, dtype=tf.int32)                        # if kb-ka < kmin then use a rejection algorithm
    INVH = tf.constant(1631.73284006, dtype=dtype)            # 1/h, h being the minimal interval range
    I0 = tf.constant(3271, dtype=tf.int32)                       # = - floor(x(1)/h)
    ALPHA = tf.constant(1.837877066409345, dtype=dtype)       # = log(2*pi)
    N = tf.constant(4000, dtype=tf.int32)                        # Index of the right tail
    yl0 = tf.constant(0.053513975472, dtype=dtype)            # y_l of the leftmost rectangle
    ylN = tf.constant(0.000914116389555, dtype=dtype)         # y_l of the rightmost rectangle
    x2 = tf.constant(x, dtype=dtype)
    yu2 = tf.constant(yu, dtype=dtype)
    ncell2 = tf.constant(ncell, dtype=tf.int32)
    return(xmin, xmax, kmin, INVH, I0, ALPHA, N, yl0, ylN, x2, yu2, ncell2)

def twoRegions(a, b, k):
    xmin, xmax, kmin, INCH, I0, ALPHA, N, yl0, ylN, x, yu, ncell = getConsts(a.dtype)

    xk = tf.gather(x, k)
    xkp1 = tf.gather(x, k+1)
    sim = xk + (xkp1-xk) * tf.random_uniform(shape=tf.shape(a), dtype=a.dtype)
    c0 = tf.logical_and(tf.greater_equal(sim, a),
                        tf.less_equal(sim, b))
    yuk = tf.gather(yu, k)
    kp1 = tf.where(tf.equal(k, N), N*tf.ones_like(k), k+1)
    yukp1 = tf.gather(yu, kp1)
    km1 = tf.where(tf.equal(k, 0), 0*tf.ones_like(k), k-1)
    yukm1 = tf.gather(yu, km1)
    simy = yuk*tf.random_uniform(shape=tf.shape(a), dtype=a.dtype)

    # Compute y_l from y_k
    useKeq0 = tf.equal(k, 0)
    useKeqN = tf.logical_and(tf.equal(k, N),
                             tf.logical_not(useKeq0))

    useleq1954 = tf.logical_and(tf.less_equal(k, 1954),
                                tf.logical_and(tf.logical_not(useKeqN),
                                               tf.logical_not(useKeq0)))
    useelse = tf.logical_and(tf.logical_not(useKeq0),
                             tf.logical_and(tf.logical_not(useKeqN),
                                            tf.logical_not(useleq1954)))

    ylk = tf.zeros_like(a)

    nKeq0 = count_nonzero(useKeq0, dtype=tf.int32, axis=-1, keep_dims=True)
    ylk = tf.cond(nKeq0[0]>0,
                  lambda: updateTensor(ylk, useKeq0, yl0*tf.ones(shape=nKeq0, dtype=a.dtype)),
                  lambda: ylk)

    nKeqN = count_nonzero(useKeqN, dtype=tf.int32, axis=-1, keep_dims=True)
    ylk = tf.cond(nKeqN[0]> 0,
                  lambda: updateTensor(ylk, useKeqN, ylN*tf.ones(nKeqN, dtype=a.dtype)),
                  lambda: ylk)

    nUseleq1954 = count_nonzero(useleq1954, dtype=tf.int32, axis=-1, keep_dims=True)
    ylk = tf.cond(nUseleq1954[0] > 0,
                  lambda: updateTensor(ylk, useleq1954, tf.gather_nd(yukm1, tf.where(useleq1954))),
                  lambda: ylk)

    nUseelse = count_nonzero(useelse, dtype=tf.int32, axis=-1, keep_dims=True)
    ylk = tf.cond(nUseelse[0] > 0,
                  lambda: updateTensor(ylk, useelse, tf.gather_nd(yukp1, tf.where(useelse))),
                  lambda: ylk)

    c1 = tf.logical_or(tf.less(simy, ylk),
                       tf.less((sim**2 + 2*tf.log(simy) + ALPHA), 0))
    r = sim
    accepted = tf.logical_and(c0, c1)
    return(r, accepted)


def allOther(a, b, k):
    xmin, xmax, kmin, INVH, I0, ALPHA, N, yl0, ylN, x, yu, ncell = getConsts(a.dtype)

    u = tf.random_uniform(shape=tf.shape(a), dtype=a.dtype)
    #yuk = tf.gather(yu, tf.where(k<0, k+4001, k))

    yuk = tf.gather(yu, k)
    kp1 = tf.where(tf.equal(k, N), N*tf.ones_like(k), k+1)
    yukp1 = tf.gather(yu, kp1)
    km1 = tf.where(tf.equal(k, 0), 0*tf.ones_like(k), k-1)
    yukm1 = tf.gather(yu, km1)


    simy = yuk * u
    xkp1 = tf.gather(x, kp1)
    xk = tf.gather(x, k)

    d = xkp1 - xk

    # Compute y_l from y_k
    useKeq1 = tf.equal(k, 1)
    useKeqN = tf.logical_and(tf.equal(k, N), tf.logical_not(useKeq1))
    useleq1954 = tf.logical_and(tf.logical_not(tf.greater(k, 1954)),
                                tf.logical_and(tf.logical_not(useKeqN),
                                               tf.logical_not(useKeq1)))
    useelse = tf.logical_and(tf.logical_not(useKeq1),
                             tf.logical_and(tf.logical_not(useKeqN),
                                            tf.logical_not(useleq1954)))

    ylk = tf.zeros_like(a)

    #ylk[useKeq0] = yl0
    nKeq1 = count_nonzero(useKeq1, dtype=tf.int32, axis=-1, keep_dims=True)
    ylk = tf.cond(nKeq1[0]>0,
                  lambda: updateTensor(ylk, useKeq1, yl0*tf.ones(shape=nKeq1, dtype=a.dtype)),
                  lambda: ylk)

    #ylk[useKeqN] = ylN
    nKeqN = count_nonzero(useKeqN, dtype=tf.int32, axis=-1, keep_dims=True)
    ylk = tf.cond(nKeqN[0]> 0,
                  lambda: updateTensor(ylk, useKeqN, ylN*tf.ones(nKeqN, dtype=a.dtype)),
                  lambda: ylk)

    #ylk[useleq1954] = yu[k[useleq1954]-1]
    nUseleq1954 = count_nonzero(useleq1954, dtype=tf.int32, axis=-1, keep_dims=True)
    ylk = tf.cond(nUseleq1954[0] > 0,
                  lambda: updateTensor(ylk, useleq1954, gather_nd(yukm1, tf.where(useleq1954))),
                  lambda: ylk)

    #ylk[useelse] = yu[k[useelse]+1]
    nUseelse = count_nonzero(useelse, dtype=tf.int32, axis=-1, keep_dims=True)
    ylk = tf.cond(nUseelse[0] > 0,
                  lambda: updateTensor(ylk, useelse, gather_nd(yukp1, tf.where(useelse))),
                  lambda: ylk)

    c0 = tf.less(simy, ylk)
    r = tf.zeros_like(a)
    r = updateTensor(r, c0, tf.gather(xk + u*d*yuk/ylk, tf.where(c0))[..., 0])
    #r[c0] = (xk + u*d*yuk/ylk)[c0]

    sim = xk + d * tf.random_uniform(shape=tf.shape(a), dtype=a.dtype)
    c1 = tf.logical_and(tf.less((sim**2 + 2*tf.log(simy) + ALPHA), 0),
                        tf.logical_not(c0))
    r = updateTensor(r, c1, tf.gather(sim, tf.where(c1))[..., 0])
    #r[c1] = sim[c1]

    accepted = tf.logical_or(c0, c1)
    return(r, accepted)


def chopin(aAll, bAll):
    dtype = aAll.dtype
    rAll = tf.zeros_like(aAll)
    # Design variables
    xmin, xmax, kmin, INVH, I0, ALPHA, N, yl0, ylN, x, yu, ncell = getConsts(aAll.dtype)

    # Compute ka and kb
    i = I0 + tf.cast(tf.floor(aAll*INVH), dtype=tf.int32)
    i = tf.where(tf.less(i, 0), i+8961, i)
    ka = gather(ncell, i)                   # not: +1 due to index offset in Matlab ;-)

    kb = tf.zeros_like(ka)

    # kb[bAll>=xmax] = N
    nBAllGtXmax = count_nonzero(tf.greater_equal(bAll, xmax), dtype=tf.int32, axis=-1, keep_dims=True)
    kb = updateTensor(kb, bAll>=xmax, N*tf.ones(nBAllGtXmax, dtype=tf.int32))

    i = I0 + tf.cast(tf.floor(bAll*INVH), dtype=tf.int32)
    i = tf.where(i<0, i+8961, i)
    #kb[bAll<xmax] = ncell[i[bAll<xmax]]
    whereBAllLtXmax = tf.where(bAll<xmax)
    kb = updateTensor(kb, bAll<xmax, gather_nd(ncell, gather(i, whereBAllLtXmax)))

    ## rejection sampling
    # If |b-a| is small, use rejection algorithm with a truncated exponential proposal
    useRejectionSamplingChopin = tf.logical_and(tf.less(tf.abs(kb-ka), kmin),
                                                tf.greater(tf.abs(aAll), 0.1))
    usePpfChopin = tf.logical_and(tf.less(tf.abs(kb-ka), kmin),
                                  tf.less_equal(tf.abs(aAll), 0.1))

    ### useRejectionSamplingChopin
    a = tf.gather(aAll, tf.where(useRejectionSamplingChopin))[..., 0]
    b = tf.gather(bAll, tf.where(useRejectionSamplingChopin))[..., 0]
    nRejectionSamplingChopin = count_nonzero(useRejectionSamplingChopin, dtype=tf.int32, axis=-1, keep_dims=True)
    rAll = tf.cond(nRejectionSamplingChopin[0] > 0,
                   lambda: updateTensor(rAll, useRejectionSamplingChopin, rejectionSamplingExp(a, b)),
                   lambda: rAll)

    ### usePpfChopin
    a = tf.gather(aAll, tf.where(usePpfChopin))[..., 0]
    b = tf.gather(bAll, tf.where(usePpfChopin))[..., 0]
    nPpfChopin = count_nonzero(usePpfChopin, dtype=tf.int32, axis=-1, keep_dims=True)
    rAll = tf.cond(nPpfChopin[0] > 0,
                   lambda: updateTensor(rAll, usePpfChopin, ppf(a, b)),
                   lambda: rAll)

    useSamplingInteger = tf.logical_not(tf.logical_or(useRejectionSamplingChopin, usePpfChopin))
    kAll = tf.zeros(shape=tf.shape(aAll), dtype=tf.int32)
    acceptedAll = tf.zeros(shape=tf.shape(aAll), dtype=tf.int32)

    nNotUseSamplingInteger = count_nonzero(tf.logical_not(useSamplingInteger), dtype=tf.int32, axis=-1, keep_dims=True)
    acceptedAll = updateTensor(acceptedAll,
                               tf.logical_not(useSamplingInteger),
                               tf.ones(nNotUseSamplingInteger, dtype=tf.int32))

    def notAccepted(rAll, acceptedAll, kAll):
        return(tf.logical_not(tf.reduce_all(tf.equal(acceptedAll, 1))))

    def body(rAll, acceptedAll, kAll):
        # Sample integer between ka and kb
        # Note that while matlab randi has including border, for numpy the high
        # border is exclusive. Hence add one.
        kAllNotAccepted = randint(low=gather(ka, tf.where(tf.equal(acceptedAll, 0)))[..., 0],
                                  high=gather(kb, tf.where(tf.equal(acceptedAll, 0)))[..., 0] + 1)

        kAll = updateTensor(kAll, tf.equal(acceptedAll, 0), kAllNotAccepted)

        notAcceptedAll = tf.equal(acceptedAll, 0)
        useRightTail = tf.logical_and(useSamplingInteger,
                                      tf.logical_and(notAcceptedAll,
                                                     tf.equal(kAll, N)))
        useTwoRegions = tf.logical_and(useSamplingInteger,
                                       tf.logical_and(notAcceptedAll,
                                                      tf.logical_and(tf.logical_not(tf.equal(kAll, N)),
                                                                     tf.logical_or(tf.less_equal(kAll, ka+2),
                                                                                   tf.logical_and(tf.greater_equal(kAll, kb),
                                                                                                  tf.less(bAll, xmax)))))) #### ka
        useAllOther = tf.logical_and(useSamplingInteger,
                                     tf.logical_and(notAcceptedAll,
                                                    tf.logical_and(tf.logical_not(useRightTail),
                                                                   tf.logical_not(useTwoRegions))))


        a = tf.gather(aAll, tf.where(useRightTail))[..., 0]
        b = tf.gather(bAll, tf.where(useRightTail))[..., 0]
        r, accepted = rightTail(a, b)
        rAll = updateTensor(rAll, useRightTail, r)

        acceptedAll = updateTensor(acceptedAll,
                                   useRightTail,
                                   tf.cast(accepted, dtype=tf.int32))

        a = tf.gather(aAll, tf.where(useTwoRegions))[..., 0]
        b = tf.gather(bAll, tf.where(useTwoRegions))[..., 0]
        k = gather(kAll, tf.where(useTwoRegions))[..., 0]
        r, accepted = twoRegions(a, b, k)
        r = updateTensor(r, tf.logical_not(accepted),
                         tf.ones(tf.reduce_sum(tf.cast(tf.logical_not(accepted), dtype=tf.int32), keep_dims=True),
                                 dtype=r.dtype))

        rAll = updateTensor(rAll, useTwoRegions, r)
        acceptedAll = updateTensor(acceptedAll,
                                   useTwoRegions,
                                   tf.cast(accepted, dtype=tf.int32))

        a = tf.gather(aAll, tf.where(useAllOther))[..., 0]
        b = tf.gather(bAll, tf.where(useAllOther))[..., 0]
        k = gather(kAll, tf.where(useAllOther))[..., 0]
        r, accepted = allOther(a, b, k)
        rAll = updateTensor(rAll, useAllOther, r)

        acceptedAll = updateTensor(acceptedAll,
                                   useAllOther,
                                   tf.cast(accepted, dtype=tf.int32))

        return(rAll, acceptedAll, kAll)


    rAll, acceptedAll, kAll = tf.while_loop(notAccepted, body, loop_vars=[rAll, acceptedAll, kAll])
    return(rAll, useRejectionSamplingChopin)

def rtstdnorm(aAll, bAll):
    r"""
    RTNORM    Pseudorandom numbers from a truncated (normalized) Gaussian
    distribution (i.e. rtnorm(a,b,0,1)).
    """
    rAll = tf.zeros_like(aAll)

    xmin, xmax, kmin, INVH, I0, ALPHA, N, yl0, ylN, x, yu, ncell = getConsts(aAll.dtype)

    useRejectionSamplingExp = tf.greater(aAll, xmax)
    useRejectionSamplingNorm = tf.logical_and(tf.less_equal(aAll, xmax),
                                              tf.less(aAll, xmin))
    useChopin = tf.logical_and(tf.less_equal(aAll, xmax),
                               tf.greater_equal(aAll, xmin))

    ### useRejectionSamplingExp
    a = tf.gather(aAll, tf.where(useRejectionSamplingExp))[..., 0]
    b = tf.gather(bAll, tf.where(useRejectionSamplingExp))[..., 0]
    r = rejectionSamplingExp(a, b)
    rAll = updateTensor(rAll, useRejectionSamplingExp, r)

    ### useRecetionSamplingNorm
    a = tf.gather(aAll, tf.where(useRejectionSamplingNorm))[..., 0]
    b = tf.gather(bAll, tf.where(useRejectionSamplingNorm))[..., 0]
    r = rejectionSamplingNorm(a, b)
    rAll = updateTensor(rAll, useRejectionSamplingNorm, r)

    ### useChopin
    a = tf.gather(aAll, tf.where(useChopin))[..., 0]
    b = tf.gather(bAll, tf.where(useChopin))[..., 0]
    r, useRejectionSamplingChopin = chopin(a, b)
    rAll = updateTensor(rAll, useChopin, r)
    useRejectionSamplingExp = updateTensor(useRejectionSamplingExp, useChopin, useRejectionSamplingChopin)

    return(rAll, useRejectionSamplingExp)


def rtnorm2(a=0., b=1., mu=np.array([0.]), sigma=np.array([1.]), size=1):
    assert_op = tf.Assert(tf.reduce_all(tf.equal(a, 0.)), [a], name='aaaaa')
    with tf.control_dependencies([assert_op]):
        a = a + 0.
    assert_op = tf.Assert(tf.reduce_all(sigma>0.), [sigma], name="sigma")

    mu = tf.Print(mu, [tf.reduce_max(mu), tf.reduce_min(mu)], "mu=")
    sigma = tf.Print(sigma, [tf.reduce_max(sigma), tf.reduce_min(sigma)], "sigma=")

    with tf.control_dependencies([assert_op]):
        sigma = sigma + 0.

    # Scaling
    a = (a-mu) / sigma
    b = (b-mu) / sigma

    # Check if a < b
    isValid = a < b
    aValid = tf.gather(a, tf.where(isValid))[..., 0]
    bValid = tf.gather(b, tf.where(isValid))[..., 0]

    # flip such that |a| < |b|
    flip = tf.greater(tf.abs(a), tf.abs(b))
    flipValid = tf.greater(tf.abs(aValid), tf.abs(bValid))
    mbflipped = -tf.gather(b, tf.where(flip))[..., 0]
    maflipped = -tf.gather(a, tf.where(flip))[..., 0]
    aFlipped = updateTensor(a, flip, mbflipped)
    bFlipped = updateTensor(b, flip, maflipped)

    aFlippedValid = tf.gather(aFlipped, tf.where(isValid))[..., 0]
    bFlippedValid = tf.gather(bFlipped, tf.where(isValid))[..., 0]

    assert_op = tf.Assert(tf.reduce_all(tf.equal(aFlippedValid, 0.)), [aFlippedValid], name='aaaFlippedValid')
    with tf.control_dependencies([assert_op]):
        aFlippedValid = aFlippedValid + 0.

    rValid = rtstdnorm(aFlippedValid, bFlippedValid)
    rValid = tf.where(flipValid, -rValid, rValid)

    isNotValid = tf.logical_not(isValid)
#    nNotValid = tf.cast(tf.count_nonzero(tf.cast(isNotValid, dtype=tf.float32), dtype=tf.float32, axis=-1, keep_dims=True), dtype=tf.int32)
    nNotValid = tf.expand_dims(tf.reduce_sum(tf.cast(isNotValid, dtype=tf.int32)), axis=-1)
    rNotValid = tf.ones(shape=nNotValid, dtype=a.dtype)*np.nan

    r = tf.zeros_like(a)
    r = updateTensor(r, isValid, rValid)
    r = updateTensor(r, isNotValid, rNotValid)

    # Scaling back
    r = r * sigma + mu

    r = tf.where(r>=a, r, a)
    r = tf.where(r<=b, r, b)

    return(r)


def rtnormFlipped(a=0., b=1., mu=np.array([0.]), sigma=np.array([1.]), size=1):
    A = (a-mu) / sigma
    B = (b-mu) / sigma

    assertBgA = tf.Assert(tf.reduce_all(tf.greater(B, A)), [A, B], name='BgA')
    with tf.control_dependencies([assertBgA]):
        R, useRejectionSamplingExp = rtstdnorm(A, B)

    r = tf.where(useRejectionSamplingExp, a-R*sigma**2/(a-mu), R*sigma + mu)

    r = tf.where(r>=a, r, a)
    r = tf.where(r<=b, r, b)

    assertAllZero = tf.Assert(tf.reduce_any(tf.logical_not(tf.equal(r, 0.))), [r], name='allZero')
    with tf.control_dependencies([assertAllZero]):
        r = r + 0.

    return(r)

def rtnorm(a=0., b=1., mu=np.array([0.]), sigma=np.array([1.]), size=1):
    assertSigma0 = tf.Assert(tf.reduce_all(tf.greater(sigma, 0.)), [sigma], name='sigmaNotPositive')
    assertSigma1 = tf.Assert(tf.reduce_all(tf.is_finite(sigma)), [sigma], name='sigmaNotFinite')
    assertMu = tf.Assert(tf.reduce_all(tf.is_finite(mu)), [mu], name='muNotFinite')
    assertA = tf.Assert(tf.reduce_all(tf.logical_not(tf.is_nan(a))), [a], name='aIsNan')
    assertB = tf.Assert(tf.reduce_all(tf.logical_not(tf.is_nan(b))), [b], name='bIsNan')
    assertab = tf.Assert(tf.reduce_all((tf.greater(b, a))), [a, b], name='aGreaterb')

    with tf.control_dependencies([assertSigma0, assertSigma1, assertMu, assertA, assertB, assertab]):
        # check shapes
        aOnes = tf.ones_like(a)
        bOnes = tf.ones_like(b)
        muOnes = tf.ones_like(mu)
        sigmaOnes = tf.ones_like(sigma)
        ones = aOnes*bOnes*muOnes*sigmaOnes
        a = a * ones
        b = b * ones
        mu = mu * ones
        sigma = sigma * ones

        # flip such that |a| < |b|
        flip = tf.greater(tf.abs(a), tf.abs(b))
        mbflipped = -tf.gather(b, tf.where(flip))[..., 0]
        maflipped = -tf.gather(a, tf.where(flip))[..., 0]
        aFlipped = updateTensor(a, flip, mbflipped)
        bFlipped = updateTensor(b, flip, maflipped)
        mmuFlipped = -tf.gather(mu, tf.where(flip))[..., 0]
        muFlipped = updateTensor(mu, flip, mmuFlipped)

        # sample
        rFlipped = rtnormFlipped(aFlipped, bFlipped, mu=muFlipped, sigma=sigma, size=size)

        # flip back
        r = tf.where(flip, -rFlipped, rFlipped)
    return(r)

# Tables
x = array([
    -2.00443204036, -1.99990455547, -1.99541747213, -1.99096998962, \
    -1.98656133124, -1.98219074335, -1.97785749442, -1.97356087419, \
    -1.96930019287, -1.96507478031, -1.96088398528, -1.95672717477, \
    -1.95260373328, -1.9485130622, -1.94445457918, -1.94042771755, \
    -1.93643192574, -1.93246666677, -1.92853141772, -1.92462566922, \
    -1.92074892503, -1.91690070156, -1.91308052741, -1.90928794302, \
    -1.90552250025, -1.90178376197, -1.89807130174, -1.89438470345, \
    -1.89072356098, -1.88708747787, -1.88347606705, -1.8798889505, \
    -1.87632575899, -1.87278613181, -1.86926971649, -1.86577616858, \
    -1.86230515137, -1.85885633567, -1.8554293996, -1.85202402837, \
    -1.84863991405, -1.84527675539, -1.84193425762, -1.83861213227, \
    -1.83531009698, -1.83202787533, -1.82876519668, -1.825521796, \
    -1.82229741372, -1.81909179558, -1.81590469249, -1.81273586036, \
    -1.80958506, -1.80645205698, -1.8033366215, -1.80023852827, \
    -1.79715755637, -1.79409348917, -1.79104611422, -1.78801522309, \
    -1.78500061134, -1.78200207837, -1.77901942732, -1.77605246501, \
    -1.77310100183, -1.77016485166, -1.76724383175, -1.7643377627, \
    -1.7614464683, -1.75856977555, -1.75570751448, -1.75285951816, \
    -1.75002562257, -1.74720566658, -1.74439949184, -1.74160694276, \
    -1.73882786639, -1.7360621124, -1.73330953303, -1.73056998298, \
    -1.72784331941, -1.72512940185, -1.72242809217, -1.71973925449, \
    -1.71706275519, -1.7143984628, -1.71174624799, -1.70910598353, \
    -1.70647754419, -1.70386080677, -1.70125565, -1.69866195455, \
    -1.69607960292, -1.69350847947, -1.69094847035, -1.68839946345, \
    -1.6858613484, -1.68333401649, -1.68081736069, -1.67831127556, \
    -1.67581565725, -1.67333040348, -1.67085541345, -1.6683905879, \
    -1.665935829, -1.66349104035, -1.66105612696, -1.65863099522, \
    -1.65621555288, -1.65380970898, -1.65141337389, -1.64902645924, \
    -1.64664887792, -1.64428054402, -1.64192137286, -1.63957128092, \
    -1.63723018585, -1.63489800643, -1.63257466256, -1.63026007522, \
    -1.62795416649, -1.62565685948, -1.62336807836, -1.62108774828, \
    -1.61881579544, -1.61655214696, -1.61429673098, -1.61204947656, \
    -1.60981031368, -1.60757917325, -1.60535598708, -1.60314068784, \
    -1.60093320909, -1.59873348523, -1.59654145149, -1.59435704393, \
    -1.59218019943, -1.59001085565, -1.58784895103, -1.58569442477, \
    -1.58354721686, -1.581407268, -1.57927451964, -1.57714891392, \
    -1.57503039371, -1.57291890258, -1.57081438477, -1.56871678519, \
    -1.56662604942, -1.56454212368, -1.56246495486, -1.56039449044, \
    -1.55833067854, -1.55627346789, -1.55422280782, -1.55217864825, \
    -1.55014093969, -1.5481096332, -1.54608468043, -1.54406603357, \
    -1.54205364536, -1.54004746908, -1.53804745854, -1.53605356807, \
    -1.53406575252, -1.53208396723, -1.53010816806, -1.52813831134, \
    -1.52617435391, -1.52421625305, -1.52226396655, -1.52031745264, \
    -1.51837667, -1.51644157777, -1.51451213554, -1.51258830332, \
    -1.51067004156, -1.50875731112, -1.5068500733, -1.50494828979, \
    -1.50305192269, -1.50116093452, -1.49927528818, -1.49739494693, \
    -1.49551987447, -1.49365003484, -1.49178539245, -1.48992591209, \
    -1.48807155892, -1.48622229844, -1.48437809651, -1.48253891934, \
    -1.48070473348, -1.47887550581, -1.47705120356, -1.47523179427, \
    -1.47341724582, -1.47160752641, -1.46980260454, -1.46800244903, \
    -1.46620702902, -1.46441631394, -1.46263027351, -1.46084887778, \
    -1.45907209704, -1.45729990192, -1.4555322633, -1.45376915236, \
    -1.45201054053, -1.45025639954, -1.44850670139, -1.44676141832, \
    -1.44502052286, -1.44328398779, -1.44155178613, -1.43982389118, \
    -1.43810027647, -1.43638091579, -1.43466578316, -1.43295485285, \
    -1.43124809936, -1.42954549744, -1.42784702206, -1.4261526484, \
    -1.42446235191, -1.42277610822, -1.42109389321, -1.41941568296, \
    -1.41774145377, -1.41607118216, -1.41440484485, -1.41274241877, \
    -1.41108388106, -1.40942920906, -1.40777838029, -1.40613137251, \
    -1.40448816364, -1.40284873181, -1.40121305532, -1.39958111269, \
    -1.3979528826, -1.39632834393, -1.39470747574, -1.39309025725, \
    -1.39147666789, -1.38986668723, -1.38826029505, -1.38665747129, \
    -1.38505819603, -1.38346244956, -1.38187021232, -1.3802814649, \
    -1.37869618807, -1.37711436276, -1.37553597004, -1.37396099116, \
    -1.37238940752, -1.37082120066, -1.36925635228, -1.36769484423, \
    -1.36613665852, -1.36458177727, -1.3630301828, -1.36148185752, \
    -1.35993678401, -1.35839494499, -1.35685632332, -1.35532090198, \
    -1.3537886641, -1.35225959295, -1.35073367192, -1.34921088453, \
    -1.34769121444, -1.34617464545, -1.34466116145, -1.34315074649, \
    -1.34164338473, -1.34013906045, -1.33863775808, -1.33713946213, \
    -1.33564415726, -1.33415182822, -1.33266245992, -1.33117603734, \
    -1.3296925456, -1.32821196994, -1.32673429568, -1.32525950829, \
    -1.32378759331, -1.32231853644, -1.32085232344, -1.31938894019, \
    -1.3179283727, -1.31647060705, -1.31501562944, -1.31356342618, \
    -1.31211398366, -1.31066728839, -1.30922332698, -1.30778208612, \
    -1.30634355261, -1.30490771336, -1.30347455533, -1.30204406564, \
    -1.30061623144, -1.29919104001, -1.29776847873, -1.29634853503, \
    -1.29493119647, -1.29351645068, -1.29210428538, -1.29069468838, \
    -1.28928764758, -1.28788315096, -1.28648118658, -1.2850817426, \
    -1.28368480725, -1.28229036885, -1.2808984158, -1.27950893658, \
    -1.27812191975, -1.27673735394, -1.27535522788, -1.27397553036, \
    -1.27259825027, -1.27122337654, -1.2698508982, -1.26848080436, \
    -1.26711308419, -1.26574772695, -1.26438472195, -1.26302405859, \
    -1.26166572634, -1.26030971474, -1.25895601339, -1.25760461198, \
    -1.25625550025, -1.25490866802, -1.25356410517, -1.25222180165, \
    -1.25088174749, -1.24954393277, -1.24820834764, -1.24687498231, \
    -1.24554382707, -1.24421487225, -1.24288810826, -1.24156352558, \
    -1.24024111474, -1.23892086632, -1.23760277098, -1.23628681945, \
    -1.23497300248, -1.23366131092, -1.23235173565, -1.23104426764, \
    -1.22973889789, -1.22843561746, -1.22713441748, -1.22583528914, \
    -1.22453822366, -1.22324321234, -1.22195024653, -1.22065931762, \
    -1.21937041707, -1.2180835364, -1.21679866716, -1.21551580096, \
    -1.21423492948, -1.21295604444, -1.21167913759, -1.21040420078, \
    -1.20913122586, -1.20786020475, -1.20659112944, -1.20532399194, \
    -1.20405878432, -1.2027954987, -1.20153412724, -1.20027466216, \
    -1.19901709572, -1.19776142023, -1.19650762804, -1.19525571156, \
    -1.19400566322, -1.19275747553, -1.19151114101, -1.19026665225, \
    -1.18902400188, -1.18778318256, -1.18654418701, -1.18530700798, \
    -1.18407163828, -1.18283807074, -1.18160629825, -1.18037631374, \
    -1.17914811017, -1.17792168055, -1.17669701793, -1.1754741154, \
    -1.17425296609, -1.17303356317, -1.17181589985, -1.17059996938, \
    -1.16938576505, -1.16817328018, -1.16696250814, -1.16575344233, \
    -1.1645460762, -1.16334040321, -1.16213641689, -1.16093411079, \
    -1.1597334785, -1.15853451364, -1.15733720988, -1.1561415609, \
    -1.15494756045, -1.1537552023, -1.15256448023, -1.1513753881, \
    -1.15018791978, -1.14900206916, -1.1478178302, -1.14663519686, \
    -1.14545416315, -1.14427472312, -1.14309687083, -1.14192060039, \
    -1.14074590595, -1.13957278166, -1.13840122174, -1.13723122041, \
    -1.13606277195, -1.13489587064, -1.13373051083, -1.13256668686, \
    -1.13140439313, -1.13024362405, -1.12908437408, -1.12792663769, \
    -1.1267704094, -1.12561568374, -1.12446245528, -1.12331071862, \
    -1.12216046839, -1.12101169923, -1.11986440583, -1.1187185829, \
    -1.11757422519, -1.11643132745, -1.11528988448, -1.11414989111, \
    -1.11301134218, -1.11187423257, -1.11073855719, -1.10960431095, \
    -1.10847148882, -1.10734008578, -1.10621009684, -1.10508151703, \
    -1.10395434141, -1.10282856507, -1.10170418311, -1.10058119068, \
    -1.09945958293, -1.09833935506, -1.09722050226, -1.09610301977, \
    -1.09498690286, -1.09387214681, -1.09275874692, -1.09164669853, \
    -1.09053599698, -1.08942663766, -1.08831861598, -1.08721192734, \
    -1.08610656721, -1.08500253104, -1.08389981434, -1.08279841262, \
    -1.08169832142, -1.0805995363, -1.07950205283, -1.07840586663, \
    -1.07731097332, -1.07621736855, -1.07512504799, -1.07403400732, \
    -1.07294424226, -1.07185574854, -1.07076852192, -1.06968255816, \
    -1.06859785307, -1.06751440246, -1.06643220217, -1.06535124805, \
    -1.06427153597, -1.06319306184, -1.06211582157, -1.06103981109, \
    -1.05996502636, -1.05889146336, -1.05781911808, -1.05674798653, \
    -1.05567806475, -1.05460934878, -1.0535418347, -1.0524755186, \
    -1.05141039657, -1.05034646476, -1.04928371929, -1.04822215635, \
    -1.04716177209, -1.04610256273, -1.04504452448, -1.04398765357, \
    -1.04293194626, -1.04187739881, -1.04082400752, -1.03977176868, \
    -1.03872067861, -1.03767073366, -1.03662193018, -1.03557426455, \
    -1.03452773314, -1.03348233237, -1.03243805866, -1.03139490845, \
    -1.03035287819, -1.02931196435, -1.02827216342, -1.02723347191, \
    -1.02619588633, -1.02515940322, -1.02412401912, -1.02308973062, \
    -1.02205653428, -1.02102442671, -1.01999340452, -1.01896346433, \
    -1.01793460279, -1.01690681657, -1.01588010232, -1.01485445675, \
    -1.01382987655, -1.01280635844, -1.01178389916, -1.01076249545, \
    -1.00974214407, -1.0087228418, -1.00770458543, -1.00668737176, \
    -1.00567119762, -1.00465605983, -1.00364195524, -1.00262888071, \
    -1.00161683312, -1.00060580935, -0.999595806306, -0.9985868209, \
    -0.997578850062, -0.996571890733, -0.995565939868, -0.994560994436, \
    -0.993557051418, -0.992554107808, -0.991552160613, -0.990551206854, \
    -0.989551243564, -0.988552267788, -0.987554276585, -0.986557267027, \
    -0.985561236196, -0.984566181188, -0.983572099113, -0.982578987091, \
    -0.981586842254, -0.980595661749, -0.979605442731, -0.978616182371, \
    -0.977627877849, -0.976640526359, -0.975654125105, -0.974668671305, \
    -0.973684162186, -0.972700594988, -0.971717966963, -0.970736275374, \
    -0.969755517495, -0.968775690612, -0.967796792022, -0.966818819033, \
    -0.965841768964, -0.964865639146, -0.963890426921, -0.962916129641, \
    -0.961942744669, -0.960970269379, -0.959998701157, -0.959028037398, \
    -0.958058275508, -0.957089412906, -0.956121447017, -0.955154375281, \
    -0.954188195145, -0.953222904069, -0.952258499521, -0.951294978982, \
    -0.95033233994, -0.949370579895, -0.948409696358, -0.947449686847, \
    -0.946490548893, -0.945532280036, -0.944574877824, -0.943618339818, \
    -0.942662663587, -0.941707846709, -0.940753886774, -0.939800781378, \
    -0.93884852813, -0.937897124647, -0.936946568555, -0.935996857491, \
    -0.9350479891, -0.934099961035, -0.933152770962, -0.932206416553, \
    -0.931260895491, -0.930316205466, -0.929372344179, -0.928429309338, \
    -0.927487098664, -0.926545709881, -0.925605140727, -0.924665388946, \
    -0.923726452292, -0.922788328527, -0.921851015421, -0.920914510754, \
    -0.919978812315, -0.919043917899, -0.918109825313, -0.917176532369, \
    -0.916244036888, -0.915312336703, -0.91438142965, -0.913451313577, \
    -0.912521986339, -0.911593445799, -0.910665689828, -0.909738716305, \
    -0.908812523118, -0.907887108163, -0.906962469342, -0.906038604567, \
    -0.905115511758, -0.90419318884, -0.90327163375, -0.902350844428, \
    -0.901430818827, -0.900511554903, -0.899593050622, -0.898675303958, \
    -0.897758312891, -0.896842075409, -0.895926589508, -0.895011853191, \
    -0.894097864469, -0.893184621359, -0.892272121887, -0.891360364086, \
    -0.890449345995, -0.889539065661, -0.888629521138, -0.887720710488, \
    -0.886812631779, -0.885905283087, -0.884998662493, -0.884092768089, \
    -0.883187597969, -0.882283150238, -0.881379423006, -0.88047641439, \
    -0.879574122514, -0.878672545509, -0.877771681512, -0.876871528668, \
    -0.875972085128, -0.875073349049, -0.874175318595, -0.873277991937, \
    -0.872381367254, -0.871485442727, -0.870590216549, -0.869695686916, \
    -0.868801852031, -0.867908710104, -0.86701625935, -0.866124497993, \
    -0.865233424261, -0.864343036389, -0.863453332618, -0.862564311196, \
    -0.861675970376, -0.860788308418, -0.859901323588, -0.859015014157, \
    -0.858129378404, -0.857244414613, -0.856360121074, -0.855476496083, \
    -0.854593537942, -0.853711244958, -0.852829615446, -0.851948647726, \
    -0.851068340122, -0.850188690965, -0.849309698594, -0.84843136135, \
    -0.847553677583, -0.846676645646, -0.845800263899, -0.844924530708, \
    -0.844049444444, -0.843175003483, -0.842301206208, -0.841428051007, \
    -0.840555536273, -0.839683660404, -0.838812421805, -0.837941818885, \
    -0.83707185006, -0.83620251375, -0.83533380838, -0.834465732382, \
    -0.833598284192, -0.832731462252, -0.831865265009, -0.830999690914, \
    -0.830134738426, -0.829270406006, -0.828406692123, -0.827543595248, \
    -0.826681113861, -0.825819246443, -0.824957991484, -0.824097347476, \
    -0.823237312917, -0.82237788631, -0.821519066163, -0.82066085099, \
    -0.819803239307, -0.818946229639, -0.818089820512, -0.817234010459, \
    -0.816378798017, -0.815524181729, -0.814670160142, -0.813816731806, \
    -0.812963895279, -0.812111649122, -0.8112599919, -0.810408922185, \
    -0.80955843855, -0.808708539576, -0.807859223848, -0.807010489955, \
    -0.806162336489, -0.805314762049, -0.804467765238, -0.803621344663, \
    -0.802775498936, -0.801930226672, -0.801085526493, -0.800241397023, \
    -0.799397836891, -0.798554844732, -0.797712419183, -0.796870558888, \
    -0.796029262492, -0.795188528648, -0.79434835601, -0.793508743238, \
    -0.792669688996, -0.791831191953, -0.790993250781, -0.790155864155, \
    -0.789319030758, -0.788482749274, -0.787647018393, -0.786811836806, \
    -0.785977203212, -0.785143116312, -0.784309574812, -0.783476577421, \
    -0.782644122852, -0.781812209823, -0.780980837056, -0.780150003277, \
    -0.779319707213, -0.7784899476, -0.777660723175, -0.776832032678, \
    -0.776003874855, -0.775176248455, -0.774349152231, -0.773522584939, \
    -0.772696545341, -0.7718710322, -0.771046044284, -0.770221580367, \
    -0.769397639223, -0.768574219631, -0.767751320376, -0.766928940243, \
    -0.766107078024, -0.765285732513, -0.764464902507, -0.763644586809, \
    -0.762824784223, -0.762005493558, -0.761186713627, -0.760368443246, \
    -0.759550681234, -0.758733426414, -0.757916677614, -0.757100433662, \
    -0.756284693394, -0.755469455646, -0.754654719259, -0.753840483077, \
    -0.753026745948, -0.752213506722, -0.751400764255, -0.750588517404, \
    -0.74977676503, -0.748965505998, -0.748154739176, -0.747344463435, \
    -0.746534677651, -0.7457253807, -0.744916571465, -0.74410824883, \
    -0.743300411682, -0.742493058914, -0.741686189419, -0.740879802096, \
    -0.740073895844, -0.739268469569, -0.738463522177, -0.737659052579, \
    -0.736855059689, -0.736051542423, -0.735248499702, -0.734445930447, \
    -0.733643833587, -0.73284220805, -0.732041052768, -0.731240366677, \
    -0.730440148716, -0.729640397826, -0.728841112951, -0.728042293041, \
    -0.727243937044, -0.726446043916, -0.725648612612, -0.724851642093, \
    -0.724055131321, -0.723259079262, -0.722463484884, -0.721668347159, \
    -0.720873665062, -0.720079437569, -0.719285663661, -0.718492342322, \
    -0.717699472536, -0.716907053294, -0.716115083586, -0.715323562408, \
    -0.714532488756, -0.713741861631, -0.712951680037, -0.712161942978, \
    -0.711372649463, -0.710583798504, -0.709795389115, -0.709007420313, \
    -0.708219891118, -0.707432800551, -0.706646147638, -0.705859931406, \
    -0.705074150887, -0.704288805113, -0.70350389312, -0.702719413947, \
    -0.701935366634, -0.701151750226, -0.700368563769, -0.699585806312, \
    -0.698803476906, -0.698021574607, -0.69724009847, -0.696459047555, \
    -0.695678420925, -0.694898217643, -0.694118436777, -0.693339077397, \
    -0.692560138575, -0.691781619384, -0.691003518904, -0.690225836212, \
    -0.689448570392, -0.688671720529, -0.687895285708, -0.687119265021, \
    -0.686343657558, -0.685568462415, -0.684793678689, -0.684019305478, \
    -0.683245341885, -0.682471787013, -0.68169863997, -0.680925899864, \
    -0.680153565806, -0.679381636911, -0.678610112294, -0.677838991074, \
    -0.677068272372, -0.67629795531, -0.675528039013, -0.674758522611, \
    -0.673989405232, -0.67322068601, -0.672452364078, -0.671684438573, \
    -0.670916908635, -0.670149773405, -0.669383032026, -0.668616683646, \
    -0.66785072741, -0.667085162471, -0.666319987981, -0.665555203094, \
    -0.664790806967, -0.66402679876, -0.663263177633, -0.662499942752, \
    -0.66173709328, -0.660974628386, -0.66021254724, -0.659450849015, \
    -0.658689532883, -0.657928598023, -0.657168043612, -0.656407868831, \
    -0.655648072862, -0.654888654892, -0.654129614105, -0.653370949693, \
    -0.652612660844, -0.651854746754, -0.651097206616, -0.650340039629, \
    -0.64958324499, -0.648826821903, -0.648070769569, -0.647315087195, \
    -0.646559773988, -0.645804829157, -0.645050251913, -0.64429604147, \
    -0.643542197043, -0.642788717849, -0.642035603108, -0.641282852041, \
    -0.640530463871, -0.639778437823, -0.639026773124, -0.638275469004, \
    -0.637524524692, -0.636773939423, -0.636023712429, -0.63527384295, \
    -0.634524330221, -0.633775173485, -0.633026371984, -0.632277924961, \
    -0.631529831662, -0.630782091336, -0.630034703232, -0.629287666601, \
    -0.628540980698, -0.627794644778, -0.627048658096, -0.626303019913, \
    -0.625557729489, -0.624812786087, -0.62406818897, -0.623323937406, \
    -0.622580030661, -0.621836468005, -0.621093248711, -0.62035037205, \
    -0.619607837299, -0.618865643733, -0.618123790632, -0.617382277275, \
    -0.616641102944, -0.615900266923, -0.615159768498, -0.614419606955, \
    -0.613679781584, -0.612940291674, -0.612201136518, -0.61146231541, \
    -0.610723827646, -0.609985672522, -0.609247849338, -0.608510357395, \
    -0.607773195994, -0.607036364439, -0.606299862036, -0.605563688093, \
    -0.604827841918, -0.604092322821, -0.603357130115, -0.602622263113, \
    -0.601887721131, -0.601153503486, -0.600419609496, -0.599686038481, \
    -0.598952789763, -0.598219862666, -0.597487256514, -0.596754970634, \
    -0.596023004354, -0.595291357003, -0.594560027913, -0.593829016416, \
    -0.593098321847, -0.592367943541, -0.591637880836, -0.590908133071, \
    -0.590178699585, -0.589449579722, -0.588720772824, -0.587992278236, \
    -0.587264095305, -0.586536223378, -0.585808661806, -0.585081409939, \
    -0.584354467129, -0.58362783273, -0.582901506099, -0.58217548659, \
    -0.581449773564, -0.580724366379, -0.579999264397, -0.57927446698, \
    -0.578549973492, -0.5778257833, -0.577101895769, -0.576378310269, \
    -0.575655026169, -0.57493204284, -0.574209359655, -0.573486975988, \
    -0.572764891214, -0.57204310471, -0.571321615855, -0.570600424028, \
    -0.56987952861, -0.569158928984, -0.568438624533, -0.567718614641, \
    -0.566998898697, -0.566279476088, -0.565560346202, -0.56484150843, \
    -0.564122962165, -0.563404706799, -0.562686741727, -0.561969066345, \
    -0.56125168005, -0.560534582241, -0.559817772317, -0.559101249681, \
    -0.558385013733, -0.557669063878, -0.556953399521, -0.556238020069, \
    -0.555522924929, -0.55480811351, -0.554093585223, -0.553379339478, \
    -0.552665375689, -0.551951693269, -0.551238291635, -0.550525170202, \
    -0.549812328389, -0.549099765614, -0.548387481299, -0.547675474863, \
    -0.546963745731, -0.546252293327, -0.545541117075, -0.544830216402, \
    -0.544119590737, -0.543409239507, -0.542699162143, -0.541989358077, \
    -0.541279826741, -0.540570567568, -0.539861579995, -0.539152863456, \
    -0.53844441739, -0.537736241235, -0.537028334431, -0.536320696418, \
    -0.535613326639, -0.534906224537, -0.534199389557, -0.533492821143, \
    -0.532786518743, -0.532080481805, -0.531374709778, -0.530669202111, \
    -0.529963958257, -0.529258977668, -0.528554259797, -0.5278498041, \
    -0.527145610031, -0.526441677048, -0.52573800461, -0.525034592175, \
    -0.524331439204, -0.523628545158, -0.5229259095, -0.522223531693, \
    -0.521521411203, -0.520819547494, -0.520117940035, -0.519416588293, \
    -0.518715491738, -0.518014649839, -0.517314062067, -0.516613727896, \
    -0.515913646798, -0.515213818248, -0.514514241722, -0.513814916696, \
    -0.513115842648, -0.512417019057, -0.511718445402, -0.511020121164, \
    -0.510322045826, -0.509624218869, -0.508926639778, -0.508229308038, \
    -0.507532223135, -0.506835384556, -0.506138791788, -0.505442444322, \
    -0.504746341647, -0.504050483254, -0.503354868635, -0.502659497283, \
    -0.501964368692, -0.501269482359, -0.500574837777, -0.499880434446, \
    -0.499186271862, -0.498492349525, -0.497798666935, -0.497105223592, \
    -0.496412018999, -0.49571905266, -0.495026324076, -0.494333832755, \
    -0.493641578201, -0.492949559921, -0.492257777423, -0.491566230217, \
    -0.49087491781, -0.490183839715, -0.489492995442, -0.488802384505, \
    -0.488112006416, -0.487421860691, -0.486731946843, -0.48604226439, \
    -0.48535281285, -0.484663591739, -0.483974600576, -0.483285838883, \
    -0.48259730618, -0.481909001988, -0.48122092583, -0.480533077229, \
    -0.479845455711, -0.479158060801, -0.478470892024, -0.477783948909, \
    -0.477097230982, -0.476410737773, -0.475724468813, -0.47503842363, \
    -0.474352601759, -0.473667002729, -0.472981626076, -0.472296471333, \
    -0.471611538035, -0.470926825718, -0.470242333919, -0.469558062177, \
    -0.468874010028, -0.468190177013, -0.467506562672, -0.466823166546, \
    -0.466139988176, -0.465457027107, -0.46477428288, -0.464091755042, \
    -0.463409443136, -0.46272734671, -0.46204546531, -0.461363798483, \
    -0.460682345779, -0.460001106748, -0.459320080938, -0.458639267901, \
    -0.45795866719, -0.457278278357, -0.456598100954, -0.455918134538, \
    -0.455238378662, -0.454558832883, -0.453879496757, -0.453200369842, \
    -0.452521451697, -0.45184274188, -0.45116423995, -0.45048594547, \
    -0.449807858, -0.449129977103, -0.448452302341, -0.447774833279, \
    -0.44709756948, -0.446420510511, -0.445743655937, -0.445067005325, \
    -0.444390558244, -0.44371431426, -0.443038272944, -0.442362433866, \
    -0.441686796595, -0.441011360704, -0.440336125765, -0.43966109135, \
    -0.438986257034, -0.43831162239, -0.437637186994, -0.436962950421, \
    -0.436288912249, -0.435615072055, -0.434941429417, -0.434267983913, \
    -0.433594735123, -0.432921682628, -0.432248826008, -0.431576164846, \
    -0.430903698722, -0.430231427222, -0.429559349928, -0.428887466426, \
    -0.4282157763, -0.427544279136, -0.426872974521, -0.426201862043, \
    -0.42553094129, -0.42486021185, -0.424189673313, -0.423519325269, \
    -0.422849167309, -0.422179199024, -0.421509420007, -0.420839829851, \
    -0.420170428149, -0.419501214496, -0.418832188486, -0.418163349716, \
    -0.417494697781, -0.416826232279, -0.416157952806, -0.415489858963, \
    -0.414821950346, -0.414154226557, -0.413486687196, -0.412819331863, \
    -0.41215216016, -0.41148517169, -0.410818366055, -0.410151742859, \
    -0.409485301706, -0.408819042201, -0.40815296395, -0.407487066559, \
    -0.406821349634, -0.406155812784, -0.405490455615, -0.404825277738, \
    -0.404160278761, -0.403495458294, -0.402830815949, -0.402166351335, \
    -0.401502064066, -0.400837953753, -0.40017402001, -0.399510262451, \
    -0.398846680689, -0.39818327434, -0.397520043019, -0.396856986343, \
    -0.396194103929, -0.395531395393, -0.394868860354, -0.394206498431, \
    -0.393544309243, -0.392882292409, -0.392220447549, -0.391558774287, \
    -0.390897272241, -0.390235941036, -0.389574780293, -0.388913789636, \
    -0.38825296869, -0.387592317078, -0.386931834425, -0.386271520359, \
    -0.385611374504, -0.384951396488, -0.384291585938, -0.383631942482, \
    -0.382972465749, -0.382313155368, -0.381654010969, -0.380995032182, \
    -0.380336218639, -0.379677569969, -0.379019085806, -0.378360765783, \
    -0.377702609531, -0.377044616686, -0.37638678688, -0.37572911975, \
    -0.37507161493, -0.374414272056, -0.373757090765, -0.373100070693, \
    -0.372443211479, -0.37178651276, -0.371129974175, -0.370473595364, \
    -0.369817375965, -0.369161315619, -0.368505413967, -0.36784967065, \
    -0.367194085311, -0.36653865759, -0.365883387132, -0.36522827358, \
    -0.364573316578, -0.36391851577, -0.363263870801, -0.362609381316, \
    -0.361955046963, -0.361300867386, -0.360646842235, -0.359992971155, \
    -0.359339253795, -0.358685689804, -0.358032278831, -0.357379020525, \
    -0.356725914537, -0.356072960516, -0.355420158116, -0.354767506986, \
    -0.354115006779, -0.353462657149, -0.352810457747, -0.352158408227, \
    -0.351506508245, -0.350854757453, -0.350203155508, -0.349551702065, \
    -0.34890039678, -0.348249239309, -0.34759822931, -0.346947366441, \
    -0.346296650358, -0.345646080722, -0.344995657189, -0.344345379421, \
    -0.343695247078, -0.343045259818, -0.342395417304, -0.341745719196, \
    -0.341096165157, -0.340446754849, -0.339797487934, -0.339148364076, \
    -0.338499382938, -0.337850544184, -0.33720184748, -0.33655329249, \
    -0.335904878879, -0.335256606314, -0.334608474462, -0.333960482988, \
    -0.33331263156, -0.332664919846, -0.332017347514, -0.331369914234, \
    -0.330722619673, -0.330075463502, -0.329428445391, -0.328781565009, \
    -0.328134822029, -0.32748821612, -0.326841746956, -0.326195414208, \
    -0.325549217549, -0.324903156652, -0.32425723119, -0.323611440838, \
    -0.322965785269, -0.322320264159, -0.321674877183, -0.321029624016, \
    -0.320384504335, -0.319739517815, -0.319094664135, -0.318449942971, \
    -0.317805354, -0.317160896902, -0.316516571355, -0.315872377037, \
    -0.315228313629, -0.314584380809, -0.313940578259, -0.313296905659, \
    -0.312653362689, -0.312009949032, -0.311366664369, -0.310723508383, \
    -0.310080480756, -0.309437581171, -0.308794809313, -0.308152164863, \
    -0.307509647508, -0.306867256932, -0.306224992819, -0.305582854855, \
    -0.304940842726, -0.304298956119, -0.303657194719, -0.303015558215, \
    -0.302374046293, -0.301732658641, -0.301091394947, -0.3004502549, \
    -0.29980923819, -0.299168344504, -0.298527573533, -0.297886924968, \
    -0.297246398498, -0.296605993814, -0.295965710609, -0.295325548572, \
    -0.294685507396, -0.294045586775, -0.293405786399, -0.292766105963, \
    -0.292126545159, -0.291487103683, -0.290847781227, -0.290208577487, \
    -0.289569492157, -0.288930524932, -0.288291675509, -0.287652943584, \
    -0.287014328852, -0.28637583101, -0.285737449756, -0.285099184787, \
    -0.2844610358, -0.283823002495, -0.283185084568, -0.28254728172, \
    -0.28190959365, -0.281272020056, -0.280634560639, -0.279997215099, \
    -0.279359983137, -0.278722864454, -0.278085858751, -0.277448965729, \
    -0.27681218509, -0.276175516537, -0.275538959773, -0.2749025145, \
    -0.274266180422, -0.273629957242, -0.272993844665, -0.272357842394, \
    -0.271721950134, -0.271086167591, -0.270450494469, -0.269814930474, \
    -0.269179475313, -0.268544128691, -0.267908890315, -0.267273759892, \
    -0.26663873713, -0.266003821735, -0.265369013416, -0.264734311881, \
    -0.264099716838, -0.263465227997, -0.262830845067, -0.262196567757, \
    -0.261562395776, -0.260928328836, -0.260294366646, -0.259660508917, \
    -0.25902675536, -0.258393105687, -0.25775955961, -0.25712611684, \
    -0.256492777089, -0.25585954007, -0.255226405497, -0.254593373082, \
    -0.253960442538, -0.253327613581, -0.252694885923, -0.252062259279, \
    -0.251429733364, -0.250797307892, -0.25016498258, -0.249532757143, \
    -0.248900631296, -0.248268604756, -0.24763667724, -0.247004848463, \
    -0.246373118143, -0.245741485998, -0.245109951745, -0.244478515102, \
    -0.243847175788, -0.24321593352, -0.242584788017, -0.241953738999, \
    -0.241322786185, -0.240691929294, -0.240061168047, -0.239430502163, \
    -0.238799931363, -0.238169455368, -0.237539073899, -0.236908786677, \
    -0.236278593424, -0.235648493861, -0.235018487711, -0.234388574696, \
    -0.233758754538, -0.233129026961, -0.232499391688, -0.231869848442, \
    -0.231240396947, -0.230611036927, -0.229981768106, -0.229352590209, \
    -0.22872350296, -0.228094506085, -0.227465599309, -0.226836782357, \
    -0.226208054955, -0.22557941683, -0.224950867708, -0.224322407315, \
    -0.223694035378, -0.223065751624, -0.222437555781, -0.221809447576, \
    -0.221181426737, -0.220553492993, -0.219925646071, -0.219297885701, \
    -0.21867021161, -0.218042623529, -0.217415121186, -0.216787704312, \
    -0.216160372636, -0.215533125887, -0.214905963798, -0.214278886097, \
    -0.213651892517, -0.213024982787, -0.212398156639, -0.211771413806, \
    -0.211144754018, -0.210518177008, -0.209891682507, -0.209265270249, \
    -0.208638939966, -0.208012691392, -0.207386524258, -0.206760438299, \
    -0.206134433249, -0.20550850884, -0.204882664808, -0.204256900887, \
    -0.203631216811, -0.203005612315, -0.202380087133, -0.201754641003, \
    -0.201129273658, -0.200503984834, -0.199878774268, -0.199253641695, \
    -0.198628586852, -0.198003609476, -0.197378709302, -0.196753886069, \
    -0.196129139514, -0.195504469373, -0.194879875385, -0.194255357287, \
    -0.193630914818, -0.193006547715, -0.192382255718, -0.191758038565, \
    -0.191133895995, -0.190509827747, -0.189885833561, -0.189261913176, \
    -0.188638066331, -0.188014292767, -0.187390592225, -0.186766964443, \
    -0.186143409164, -0.185519926127, -0.184896515074, -0.184273175746, \
    -0.183649907884, -0.18302671123, -0.182403585526, -0.181780530513, \
    -0.181157545935, -0.180534631532, -0.179911787049, -0.179289012227, \
    -0.17866630681, -0.178043670541, -0.177421103162, -0.176798604419, \
    -0.176176174053, -0.175553811811, -0.174931517434, -0.174309290669, \
    -0.173687131258, -0.173065038948, -0.172443013482, -0.171821054607, \
    -0.171199162066, -0.170577335606, -0.169955574973, -0.169333879911, \
    -0.168712250167, -0.168090685487, -0.167469185618, -0.166847750305, \
    -0.166226379296, -0.165605072338, -0.164983829177, -0.164362649561, \
    -0.163741533237, -0.163120479952, -0.162499489456, -0.161878561494, \
    -0.161257695816, -0.16063689217, -0.160016150304, -0.159395469966, \
    -0.158774850907, -0.158154292873, -0.157533795616, -0.156913358883, \
    -0.156292982424, -0.15567266599, -0.155052409329, -0.154432212191, \
    -0.153812074328, -0.153191995488, -0.152571975423, -0.151952013883, \
    -0.151332110619, -0.150712265381, -0.150092477921, -0.14947274799, \
    -0.148853075339, -0.148233459721, -0.147613900885, -0.146994398586, \
    -0.146374952573, -0.1457555626, -0.14513622842, -0.144516949783, \
    -0.143897726444, -0.143278558154, -0.142659444667, -0.142040385735, \
    -0.141421381113, -0.140802430553, -0.140183533808, -0.139564690633, \
    -0.138945900782, -0.138327164007, -0.137708480064, -0.137089848707, \
    -0.136471269689, -0.135852742766, -0.135234267692, -0.134615844222, \
    -0.13399747211, -0.133379151113, -0.132760880985, -0.132142661481, \
    -0.131524492358, -0.13090637337, -0.130288304273, -0.129670284824, \
    -0.129052314778, -0.128434393892, -0.127816521921, -0.127198698623, \
    -0.126580923754, -0.12596319707, -0.125345518329, -0.124727887287, \
    -0.124110303701, -0.12349276733, -0.122875277929, -0.122257835256, \
    -0.12164043907, -0.121023089128, -0.120405785187, -0.119788527006, \
    -0.119171314342, -0.118554146955, -0.117937024601, -0.117319947041, \
    -0.116702914032, -0.116085925333, -0.115468980703, -0.1148520799, \
    -0.114235222685, -0.113618408815, -0.113001638051, -0.112384910152, \
    -0.111768224876, -0.111151581985, -0.110534981238, -0.109918422394, \
    -0.109301905213, -0.108685429456, -0.108068994883, -0.107452601254, \
    -0.10683624833, -0.10621993587, -0.105603663637, -0.104987431389, \
    -0.10437123889, -0.103755085898, -0.103138972176, -0.102522897484, \
    -0.101906861584, -0.101290864237, -0.100674905205, -0.100058984249, \
    -0.0994431011311, -0.0988272556129, -0.0982114474563, -0.0975956764232, \
    -0.0969799422759, -0.0963642447764, -0.0957485836871, -0.0951329587704, \
    -0.0945173697886, -0.0939018165045, -0.0932862986806, -0.0926708160798, \
    -0.0920553684649, -0.0914399555988, -0.0908245772446, -0.0902092331655, \
    -0.0895939231246, -0.0889786468852, -0.0883634042109, -0.0877481948651, \
    -0.0871330186113, -0.0865178752133, -0.0859027644347, -0.0852876860396, \
    -0.0846726397917, -0.0840576254552, -0.0834426427941, -0.0828276915726, \
    -0.0822127715549, -0.0815978825056, -0.0809830241889, -0.0803681963694, \
    -0.0797533988117, -0.0791386312806, -0.0785238935406, -0.0779091853568, \
    -0.077294506494, -0.0766798567172, -0.0760652357914, -0.0754506434819, \
    -0.0748360795539, -0.0742215437727, -0.0736070359035, -0.072992555712, \
    -0.0723781029636, -0.0717636774239, -0.0711492788586, -0.0705349070334, \
    -0.0699205617141, -0.0693062426667, -0.068691949657, -0.0680776824512, \
    -0.0674634408152, -0.0668492245152, -0.0662350333175, -0.0656208669883, \
    -0.065006725294, -0.0643926080011, -0.0637785148759, -0.0631644456851, \
    -0.0625504001953, -0.0619363781731, -0.0613223793853, -0.0607084035987, \
    -0.0600944505801, -0.0594805200964, -0.0588666119147, -0.058252725802, \
    -0.0576388615253, -0.0570250188518, -0.0564111975488, -0.0557973973834, \
    -0.0551836181231, -0.0545698595352, -0.0539561213871, -0.0533424034463, \
    -0.0527287054803, -0.0521150272568, -0.0515013685434, -0.0508877291078, \
    -0.0502741087177, -0.0496605071409, -0.0490469241453, -0.0484333594987, \
    -0.0478198129692, -0.0472062843246, -0.0465927733331, -0.0459792797628, \
    -0.0453658033816, -0.0447523439579, -0.0441389012599, -0.0435254750557, \
    -0.0429120651138, -0.0422986712024, -0.04168529309, -0.041071930545, \
    -0.0404585833359, -0.0398452512311, -0.0392319339993, -0.0386186314091, \
    -0.0380053432289, -0.0373920692277, -0.0367788091739, -0.0361655628365, \
    -0.0355523299841, -0.0349391103856, -0.0343259038099, -0.0337127100257, \
    -0.0330995288021, -0.032486359908, -0.0318732031123, -0.0312600581842, \
    -0.0306469248925, -0.0300338030065, -0.0294206922952, -0.0288075925277, \
    -0.0281945034733, -0.0275814249011, -0.0269683565803, -0.0263552982801, \
    -0.0257422497699, -0.025129210819, -0.0245161811967, -0.0239031606722, \
    -0.0232901490151, -0.0226771459946, -0.0220641513803, -0.0214511649415, \
    -0.0208381864477, -0.0202252156684, -0.019612252373, -0.0189992963312, \
    -0.0183863473125, -0.0177734050864, -0.0171604694224, -0.0165475400903, \
    -0.0159346168595, -0.0153216994998, -0.0147087877807, -0.0140958814719, \
    -0.0134829803432, -0.0128700841641, -0.0122571927044, -0.0116443057337, \
    -0.0110314230219, -0.0104185443386, -0.00980566945358, -0.00919279813659, \
    -0.00857993015739, -0.00796706528575, -0.00735420329145, -0.00674134394428, \
    -0.00612848701402, -0.00551563227049, -0.00490277948347, -0.00428992842278, \
    -0.00367707885824, -0.00306423055966, -0.00245138329686, -0.00183853683967, \
    -0.00122569095791, -0.000612845421414, 0.0, 0.000612845421414, \
    0.00122569095791, 0.00183853683967, 0.00245138329686, 0.00306423055966, \
    0.00367707885824, 0.00428992842278, 0.00490277948347, 0.00551563227049, \
    0.00612848701402, 0.00674134394428, 0.00735420329145, 0.00796706528575, \
    0.00857993015739, 0.00919279813659, 0.00980566945358, 0.0104185443386, \
    0.0110314230219, 0.0116443057337, 0.0122571927044, 0.0128700841641, \
    0.0134829803432, 0.0140958814719, 0.0147087877807, 0.0153216994998, \
    0.0159346168595, 0.0165475400903, 0.0171604694224, 0.0177734050864, \
    0.0183863473125, 0.0189992963312, 0.019612252373, 0.0202252156684, \
    0.0208381864477, 0.0214511649415, 0.0220641513803, 0.0226771459946, \
    0.0232901490151, 0.0239031606722, 0.0245161811967, 0.025129210819, \
    0.0257422497699, 0.0263552982801, 0.0269683565803, 0.0275814249011, \
    0.0281945034733, 0.0288075925277, 0.0294206922952, 0.0300338030065, \
    0.0306469248925, 0.0312600581842, 0.0318732031123, 0.032486359908, \
    0.0330995288021, 0.0337127100257, 0.0343259038099, 0.0349391103856, \
    0.0355523299841, 0.0361655628365, 0.0367788091739, 0.0373920692277, \
    0.0380053432289, 0.0386186314091, 0.0392319339993, 0.0398452512311, \
    0.0404585833359, 0.041071930545, 0.04168529309, 0.0422986712024, \
    0.0429120651138, 0.0435254750557, 0.0441389012599, 0.0447523439579, \
    0.0453658033816, 0.0459792797628, 0.0465927733331, 0.0472062843246, \
    0.0478198129692, 0.0484333594987, 0.0490469241453, 0.0496605071409, \
    0.0502741087177, 0.0508877291078, 0.0515013685434, 0.0521150272568, \
    0.0527287054803, 0.0533424034463, 0.0539561213871, 0.0545698595352, \
    0.0551836181231, 0.0557973973834, 0.0564111975488, 0.0570250188518, \
    0.0576388615253, 0.058252725802, 0.0588666119147, 0.0594805200964, \
    0.0600944505801, 0.0607084035987, 0.0613223793853, 0.0619363781731, \
    0.0625504001953, 0.0631644456851, 0.0637785148759, 0.0643926080011, \
    0.065006725294, 0.0656208669883, 0.0662350333175, 0.0668492245152, \
    0.0674634408152, 0.0680776824512, 0.068691949657, 0.0693062426667, \
    0.0699205617141, 0.0705349070334, 0.0711492788586, 0.0717636774239, \
    0.0723781029636, 0.072992555712, 0.0736070359035, 0.0742215437727, \
    0.0748360795539, 0.0754506434819, 0.0760652357914, 0.0766798567172, \
    0.077294506494, 0.0779091853568, 0.0785238935406, 0.0791386312806, \
    0.0797533988117, 0.0803681963694, 0.0809830241889, 0.0815978825056, \
    0.0822127715549, 0.0828276915726, 0.0834426427941, 0.0840576254552, \
    0.0846726397917, 0.0852876860396, 0.0859027644347, 0.0865178752133, \
    0.0871330186113, 0.0877481948651, 0.0883634042109, 0.0889786468852, \
    0.0895939231246, 0.0902092331655, 0.0908245772446, 0.0914399555988, \
    0.0920553684649, 0.0926708160798, 0.0932862986806, 0.0939018165045, \
    0.0945173697886, 0.0951329587704, 0.0957485836871, 0.0963642447764, \
    0.0969799422759, 0.0975956764232, 0.0982114474563, 0.0988272556129, \
    0.0994431011311, 0.100058984249, 0.100674905205, 0.101290864237, \
    0.101906861584, 0.102522897484, 0.103138972176, 0.103755085898, \
    0.10437123889, 0.104987431389, 0.105603663637, 0.10621993587, \
    0.10683624833, 0.107452601254, 0.108068994883, 0.108685429456, \
    0.109301905213, 0.109918422394, 0.110534981238, 0.111151581985, \
    0.111768224876, 0.112384910152, 0.113001638051, 0.113618408815, \
    0.114235222685, 0.1148520799, 0.115468980703, 0.116085925333, \
    0.116702914032, 0.117319947041, 0.117937024601, 0.118554146955, \
    0.119171314342, 0.119788527006, 0.120405785187, 0.121023089128, \
    0.12164043907, 0.122257835256, 0.122875277929, 0.12349276733, \
    0.124110303701, 0.124727887287, 0.125345518329, 0.12596319707, \
    0.126580923754, 0.127198698623, 0.127816521921, 0.128434393892, \
    0.129052314778, 0.129670284824, 0.130288304273, 0.13090637337, \
    0.131524492358, 0.132142661481, 0.132760880985, 0.133379151113, \
    0.13399747211, 0.134615844222, 0.135234267692, 0.135852742766, \
    0.136471269689, 0.137089848707, 0.137708480064, 0.138327164007, \
    0.138945900782, 0.139564690633, 0.140183533808, 0.140802430553, \
    0.141421381113, 0.142040385735, 0.142659444667, 0.143278558154, \
    0.143897726444, 0.144516949783, 0.14513622842, 0.1457555626, \
    0.146374952573, 0.146994398586, 0.147613900885, 0.148233459721, \
    0.148853075339, 0.14947274799, 0.150092477921, 0.150712265381, \
    0.151332110619, 0.151952013883, 0.152571975423, 0.153191995488, \
    0.153812074328, 0.154432212191, 0.155052409329, 0.15567266599, \
    0.156292982424, 0.156913358883, 0.157533795616, 0.158154292873, \
    0.158774850907, 0.159395469966, 0.160016150304, 0.16063689217, \
    0.161257695816, 0.161878561494, 0.162499489456, 0.163120479952, \
    0.163741533237, 0.164362649561, 0.164983829177, 0.165605072338, \
    0.166226379296, 0.166847750305, 0.167469185618, 0.168090685487, \
    0.168712250167, 0.169333879911, 0.169955574973, 0.170577335606, \
    0.171199162066, 0.171821054607, 0.172443013482, 0.173065038948, \
    0.173687131258, 0.174309290669, 0.174931517434, 0.175553811811, \
    0.176176174053, 0.176798604419, 0.177421103162, 0.178043670541, \
    0.17866630681, 0.179289012227, 0.179911787049, 0.180534631532, \
    0.181157545935, 0.181780530513, 0.182403585526, 0.18302671123, \
    0.183649907884, 0.184273175746, 0.184896515074, 0.185519926127, \
    0.186143409164, 0.186766964443, 0.187390592225, 0.188014292767, \
    0.188638066331, 0.189261913176, 0.189885833561, 0.190509827747, \
    0.191133895995, 0.191758038565, 0.192382255718, 0.193006547715, \
    0.193630914818, 0.194255357287, 0.194879875385, 0.195504469373, \
    0.196129139514, 0.196753886069, 0.197378709302, 0.198003609476, \
    0.198628586852, 0.199253641695, 0.199878774268, 0.200503984834, \
    0.201129273658, 0.201754641003, 0.202380087133, 0.203005612315, \
    0.203631216811, 0.204256900887, 0.204882664808, 0.20550850884, \
    0.206134433249, 0.206760438299, 0.207386524258, 0.208012691392, \
    0.208638939966, 0.209265270249, 0.209891682507, 0.210518177008, \
    0.211144754018, 0.211771413806, 0.212398156639, 0.213024982787, \
    0.213651892517, 0.214278886097, 0.214905963798, 0.215533125887, \
    0.216160372636, 0.216787704312, 0.217415121186, 0.218042623529, \
    0.21867021161, 0.219297885701, 0.219925646071, 0.220553492993, \
    0.221181426737, 0.221809447576, 0.222437555781, 0.223065751624, \
    0.223694035378, 0.224322407315, 0.224950867708, 0.22557941683, \
    0.226208054955, 0.226836782357, 0.227465599309, 0.228094506085, \
    0.22872350296, 0.229352590209, 0.229981768106, 0.230611036927, \
    0.231240396947, 0.231869848442, 0.232499391688, 0.233129026961, \
    0.233758754538, 0.234388574696, 0.235018487711, 0.235648493861, \
    0.236278593424, 0.236908786677, 0.237539073899, 0.238169455368, \
    0.238799931363, 0.239430502163, 0.240061168047, 0.240691929294, \
    0.241322786185, 0.241953738999, 0.242584788017, 0.24321593352, \
    0.243847175788, 0.244478515102, 0.245109951745, 0.245741485998, \
    0.246373118143, 0.247004848463, 0.24763667724, 0.248268604756, \
    0.248900631296, 0.249532757143, 0.25016498258, 0.250797307892, \
    0.251429733364, 0.252062259279, 0.252694885923, 0.253327613581, \
    0.253960442538, 0.254593373082, 0.255226405497, 0.25585954007, \
    0.256492777089, 0.25712611684, 0.25775955961, 0.258393105687, \
    0.25902675536, 0.259660508917, 0.260294366646, 0.260928328836, \
    0.261562395776, 0.262196567757, 0.262830845067, 0.263465227997, \
    0.264099716838, 0.264734311881, 0.265369013416, 0.266003821735, \
    0.26663873713, 0.267273759892, 0.267908890315, 0.268544128691, \
    0.269179475313, 0.269814930474, 0.270450494469, 0.271086167591, \
    0.271721950134, 0.272357842394, 0.272993844665, 0.273629957242, \
    0.274266180422, 0.2749025145, 0.275538959773, 0.276175516537, \
    0.27681218509, 0.277448965729, 0.278085858751, 0.278722864454, \
    0.279359983137, 0.279997215099, 0.280634560639, 0.281272020056, \
    0.28190959365, 0.28254728172, 0.283185084568, 0.283823002495, \
    0.2844610358, 0.285099184787, 0.285737449756, 0.28637583101, \
    0.287014328852, 0.287652943584, 0.288291675509, 0.288930524932, \
    0.289569492157, 0.290208577487, 0.290847781227, 0.291487103683, \
    0.292126545159, 0.292766105963, 0.293405786399, 0.294045586775, \
    0.294685507396, 0.295325548572, 0.295965710609, 0.296605993814, \
    0.297246398498, 0.297886924968, 0.298527573533, 0.299168344504, \
    0.29980923819, 0.3004502549, 0.301091394947, 0.301732658641, \
    0.302374046293, 0.303015558215, 0.303657194719, 0.304298956119, \
    0.304940842726, 0.305582854855, 0.306224992819, 0.306867256932, \
    0.307509647508, 0.308152164863, 0.308794809313, 0.309437581171, \
    0.310080480756, 0.310723508383, 0.311366664369, 0.312009949032, \
    0.312653362689, 0.313296905659, 0.313940578259, 0.314584380809, \
    0.315228313629, 0.315872377037, 0.316516571355, 0.317160896902, \
    0.317805354, 0.318449942971, 0.319094664135, 0.319739517815, \
    0.320384504335, 0.321029624016, 0.321674877183, 0.322320264159, \
    0.322965785269, 0.323611440838, 0.32425723119, 0.324903156652, \
    0.325549217549, 0.326195414208, 0.326841746956, 0.32748821612, \
    0.328134822029, 0.328781565009, 0.329428445391, 0.330075463502, \
    0.330722619673, 0.331369914234, 0.332017347514, 0.332664919846, \
    0.33331263156, 0.333960482988, 0.334608474462, 0.335256606314, \
    0.335904878879, 0.33655329249, 0.33720184748, 0.337850544184, \
    0.338499382938, 0.339148364076, 0.339797487934, 0.340446754849, \
    0.341096165157, 0.341745719196, 0.342395417304, 0.343045259818, \
    0.343695247078, 0.344345379421, 0.344995657189, 0.345646080722, \
    0.346296650358, 0.346947366441, 0.34759822931, 0.348249239309, \
    0.34890039678, 0.349551702065, 0.350203155508, 0.350854757453, \
    0.351506508245, 0.352158408227, 0.352810457747, 0.353462657149, \
    0.354115006779, 0.354767506986, 0.355420158116, 0.356072960516, \
    0.356725914537, 0.357379020525, 0.358032278831, 0.358685689804, \
    0.359339253795, 0.359992971155, 0.360646842235, 0.361300867386, \
    0.361955046963, 0.362609381316, 0.363263870801, 0.36391851577, \
    0.364573316578, 0.36522827358, 0.365883387132, 0.36653865759, \
    0.367194085311, 0.36784967065, 0.368505413967, 0.369161315619, \
    0.369817375965, 0.370473595364, 0.371129974175, 0.37178651276, \
    0.372443211479, 0.373100070693, 0.373757090765, 0.374414272056, \
    0.37507161493, 0.37572911975, 0.37638678688, 0.377044616686, \
    0.377702609531, 0.378360765783, 0.379019085806, 0.379677569969, \
    0.380336218639, 0.380995032182, 0.381654010969, 0.382313155368, \
    0.382972465749, 0.383631942482, 0.384291585938, 0.384951396488, \
    0.385611374504, 0.386271520359, 0.386931834425, 0.387592317078, \
    0.38825296869, 0.388913789636, 0.389574780293, 0.390235941036, \
    0.390897272241, 0.391558774287, 0.392220447549, 0.392882292409, \
    0.393544309243, 0.394206498431, 0.394868860354, 0.395531395393, \
    0.396194103929, 0.396856986343, 0.397520043019, 0.39818327434, \
    0.398846680689, 0.399510262451, 0.40017402001, 0.400837953753, \
    0.401502064066, 0.402166351335, 0.402830815949, 0.403495458294, \
    0.404160278761, 0.404825277738, 0.405490455615, 0.406155812784, \
    0.406821349634, 0.407487066559, 0.40815296395, 0.408819042201, \
    0.409485301706, 0.410151742859, 0.410818366055, 0.41148517169, \
    0.41215216016, 0.412819331863, 0.413486687196, 0.414154226557, \
    0.414821950346, 0.415489858963, 0.416157952806, 0.416826232279, \
    0.417494697781, 0.418163349716, 0.418832188486, 0.419501214496, \
    0.420170428149, 0.420839829851, 0.421509420007, 0.422179199024, \
    0.422849167309, 0.423519325269, 0.424189673313, 0.42486021185, \
    0.42553094129, 0.426201862043, 0.426872974521, 0.427544279136, \
    0.4282157763, 0.428887466426, 0.429559349928, 0.430231427222, \
    0.430903698722, 0.431576164846, 0.432248826008, 0.432921682628, \
    0.433594735123, 0.434267983913, 0.434941429417, 0.435615072055, \
    0.436288912249, 0.436962950421, 0.437637186994, 0.43831162239, \
    0.438986257034, 0.43966109135, 0.440336125765, 0.441011360704, \
    0.441686796595, 0.442362433866, 0.443038272944, 0.44371431426, \
    0.444390558244, 0.445067005325, 0.445743655937, 0.446420510511, \
    0.44709756948, 0.447774833279, 0.448452302341, 0.449129977103, \
    0.449807858, 0.45048594547, 0.45116423995, 0.45184274188, \
    0.452521451697, 0.453200369842, 0.453879496757, 0.454558832883, \
    0.455238378662, 0.455918134538, 0.456598100954, 0.457278278357, \
    0.45795866719, 0.458639267901, 0.459320080938, 0.460001106748, \
    0.460682345779, 0.461363798483, 0.46204546531, 0.46272734671, \
    0.463409443136, 0.464091755042, 0.46477428288, 0.465457027107, \
    0.466139988176, 0.466823166546, 0.467506562672, 0.468190177013, \
    0.468874010028, 0.469558062177, 0.470242333919, 0.470926825718, \
    0.471611538035, 0.472296471333, 0.472981626076, 0.473667002729, \
    0.474352601759, 0.47503842363, 0.475724468813, 0.476410737773, \
    0.477097230982, 0.477783948909, 0.478470892024, 0.479158060801, \
    0.479845455711, 0.480533077229, 0.48122092583, 0.481909001988, \
    0.48259730618, 0.483285838883, 0.483974600576, 0.484663591739, \
    0.48535281285, 0.48604226439, 0.486731946843, 0.487421860691, \
    0.488112006416, 0.488802384505, 0.489492995442, 0.490183839715, \
    0.49087491781, 0.491566230217, 0.492257777423, 0.492949559921, \
    0.493641578201, 0.494333832755, 0.495026324076, 0.49571905266, \
    0.496412018999, 0.497105223592, 0.497798666935, 0.498492349525, \
    0.499186271862, 0.499880434446, 0.500574837777, 0.501269482359, \
    0.501964368692, 0.502659497283, 0.503354868635, 0.504050483254, \
    0.504746341647, 0.505442444322, 0.506138791788, 0.506835384556, \
    0.507532223135, 0.508229308038, 0.508926639778, 0.509624218869, \
    0.510322045826, 0.511020121164, 0.511718445402, 0.512417019057, \
    0.513115842648, 0.513814916696, 0.514514241722, 0.515213818248, \
    0.515913646798, 0.516613727896, 0.517314062067, 0.518014649839, \
    0.518715491738, 0.519416588293, 0.520117940035, 0.520819547494, \
    0.521521411203, 0.522223531693, 0.5229259095, 0.523628545158, \
    0.524331439204, 0.525034592175, 0.52573800461, 0.526441677048, \
    0.527145610031, 0.5278498041, 0.528554259797, 0.529258977668, \
    0.529963958257, 0.530669202111, 0.531374709778, 0.532080481805, \
    0.532786518743, 0.533492821143, 0.534199389557, 0.534906224537, \
    0.535613326639, 0.536320696418, 0.537028334431, 0.537736241235, \
    0.53844441739, 0.539152863456, 0.539861579995, 0.540570567568, \
    0.541279826741, 0.541989358077, 0.542699162143, 0.543409239507, \
    0.544119590737, 0.544830216402, 0.545541117075, 0.546252293327, \
    0.546963745731, 0.547675474863, 0.548387481299, 0.549099765614, \
    0.549812328389, 0.550525170202, 0.551238291635, 0.551951693269, \
    0.552665375689, 0.553379339478, 0.554093585223, 0.55480811351, \
    0.555522924929, 0.556238020069, 0.556953399521, 0.557669063878, \
    0.558385013733, 0.559101249681, 0.559817772317, 0.560534582241, \
    0.56125168005, 0.561969066345, 0.562686741727, 0.563404706799, \
    0.564122962165, 0.56484150843, 0.565560346202, 0.566279476088, \
    0.566998898697, 0.567718614641, 0.568438624533, 0.569158928984, \
    0.56987952861, 0.570600424028, 0.571321615855, 0.57204310471, \
    0.572764891214, 0.573486975988, 0.574209359655, 0.57493204284, \
    0.575655026169, 0.576378310269, 0.577101895769, 0.5778257833, \
    0.578549973492, 0.57927446698, 0.579999264397, 0.580724366379, \
    0.581449773564, 0.58217548659, 0.582901506099, 0.58362783273, \
    0.584354467129, 0.585081409939, 0.585808661806, 0.586536223378, \
    0.587264095305, 0.587992278236, 0.588720772824, 0.589449579722, \
    0.590178699585, 0.590908133071, 0.591637880836, 0.592367943541, \
    0.593098321847, 0.593829016416, 0.594560027913, 0.595291357003, \
    0.596023004354, 0.596754970634, 0.597487256514, 0.598219862666, \
    0.598952789763, 0.599686038481, 0.600419609496, 0.601153503486, \
    0.601887721131, 0.602622263113, 0.603357130115, 0.604092322821, \
    0.604827841918, 0.605563688093, 0.606299862036, 0.607036364439, \
    0.607773195994, 0.608510357395, 0.609247849338, 0.609985672522, \
    0.610723827646, 0.61146231541, 0.612201136518, 0.612940291674, \
    0.613679781584, 0.614419606955, 0.615159768498, 0.615900266923, \
    0.616641102944, 0.617382277275, 0.618123790632, 0.618865643733, \
    0.619607837299, 0.62035037205, 0.621093248711, 0.621836468005, \
    0.622580030661, 0.623323937406, 0.62406818897, 0.624812786087, \
    0.625557729489, 0.626303019913, 0.627048658096, 0.627794644778, \
    0.628540980698, 0.629287666601, 0.630034703232, 0.630782091336, \
    0.631529831662, 0.632277924961, 0.633026371984, 0.633775173485, \
    0.634524330221, 0.63527384295, 0.636023712429, 0.636773939423, \
    0.637524524692, 0.638275469004, 0.639026773124, 0.639778437823, \
    0.640530463871, 0.641282852041, 0.642035603108, 0.642788717849, \
    0.643542197043, 0.64429604147, 0.645050251913, 0.645804829157, \
    0.646559773988, 0.647315087195, 0.648070769569, 0.648826821903, \
    0.64958324499, 0.650340039629, 0.651097206616, 0.651854746754, \
    0.652612660844, 0.653370949693, 0.654129614105, 0.654888654892, \
    0.655648072862, 0.656407868831, 0.657168043612, 0.657928598023, \
    0.658689532883, 0.659450849015, 0.66021254724, 0.660974628386, \
    0.66173709328, 0.662499942752, 0.663263177633, 0.66402679876, \
    0.664790806967, 0.665555203094, 0.666319987981, 0.667085162471, \
    0.66785072741, 0.668616683646, 0.669383032026, 0.670149773405, \
    0.670916908635, 0.671684438573, 0.672452364078, 0.67322068601, \
    0.673989405232, 0.674758522611, 0.675528039013, 0.67629795531, \
    0.677068272372, 0.677838991074, 0.678610112294, 0.679381636911, \
    0.680153565806, 0.680925899864, 0.68169863997, 0.682471787013, \
    0.683245341885, 0.684019305478, 0.684793678689, 0.685568462415, \
    0.686343657558, 0.687119265021, 0.687895285708, 0.688671720529, \
    0.689448570392, 0.690225836212, 0.691003518904, 0.691781619384, \
    0.692560138575, 0.693339077397, 0.694118436777, 0.694898217643, \
    0.695678420925, 0.696459047555, 0.69724009847, 0.698021574607, \
    0.698803476906, 0.699585806312, 0.700368563769, 0.701151750226, \
    0.701935366634, 0.702719413947, 0.70350389312, 0.704288805113, \
    0.705074150887, 0.705859931406, 0.706646147638, 0.707432800551, \
    0.708219891118, 0.709007420313, 0.709795389115, 0.710583798504, \
    0.711372649463, 0.712161942978, 0.712951680037, 0.713741861631, \
    0.714532488756, 0.715323562408, 0.716115083586, 0.716907053294, \
    0.717699472536, 0.718492342322, 0.719285663661, 0.720079437569, \
    0.720873665062, 0.721668347159, 0.722463484884, 0.723259079262, \
    0.724055131321, 0.724851642093, 0.725648612612, 0.726446043916, \
    0.727243937044, 0.728042293041, 0.728841112951, 0.729640397826, \
    0.730440148716, 0.731240366677, 0.732041052768, 0.73284220805, \
    0.733643833587, 0.734445930447, 0.735248499702, 0.736051542423, \
    0.736855059689, 0.737659052579, 0.738463522177, 0.739268469569, \
    0.740073895844, 0.740879802096, 0.741686189419, 0.742493058914, \
    0.743300411682, 0.74410824883, 0.744916571465, 0.7457253807, \
    0.746534677651, 0.747344463435, 0.748154739176, 0.748965505998, \
    0.74977676503, 0.750588517404, 0.751400764255, 0.752213506722, \
    0.753026745948, 0.753840483077, 0.754654719259, 0.755469455646, \
    0.756284693394, 0.757100433662, 0.757916677614, 0.758733426414, \
    0.759550681234, 0.760368443246, 0.761186713627, 0.762005493558, \
    0.762824784223, 0.763644586809, 0.764464902507, 0.765285732513, \
    0.766107078024, 0.766928940243, 0.767751320376, 0.768574219631, \
    0.769397639223, 0.770221580367, 0.771046044284, 0.7718710322, \
    0.772696545341, 0.773522584939, 0.774349152231, 0.775176248455, \
    0.776003874855, 0.776832032678, 0.777660723175, 0.7784899476, \
    0.779319707213, 0.780150003277, 0.780980837056, 0.781812209823, \
    0.782644122852, 0.783476577421, 0.784309574812, 0.785143116312, \
    0.785977203212, 0.786811836806, 0.787647018393, 0.788482749274, \
    0.789319030758, 0.790155864155, 0.790993250781, 0.791831191953, \
    0.792669688996, 0.793508743238, 0.79434835601, 0.795188528648, \
    0.796029262492, 0.796870558888, 0.797712419183, 0.798554844732, \
    0.799397836891, 0.800241397023, 0.801085526493, 0.801930226672, \
    0.802775498936, 0.803621344663, 0.804467765238, 0.805314762049, \
    0.806162336489, 0.807010489955, 0.807859223848, 0.808708539576, \
    0.80955843855, 0.810408922185, 0.8112599919, 0.812111649122, \
    0.812963895279, 0.813816731806, 0.814670160142, 0.815524181729, \
    0.816378798017, 0.817234010459, 0.818089820512, 0.818946229639, \
    0.819803239307, 0.82066085099, 0.821519066163, 0.82237788631, \
    0.823237312917, 0.824097347476, 0.824957991484, 0.825819246443, \
    0.826681113861, 0.827543595248, 0.828406692123, 0.829270406006, \
    0.830134738426, 0.830999690914, 0.831865265009, 0.832731462252, \
    0.833598284192, 0.834465732382, 0.83533380838, 0.83620251375, \
    0.83707185006, 0.837941818885, 0.838812421805, 0.839683660404, \
    0.840555536273, 0.841428051007, 0.842301206208, 0.843175003483, \
    0.844049444444, 0.844924530708, 0.845800263899, 0.846676645646, \
    0.847553677583, 0.84843136135, 0.849309698594, 0.850188690965, \
    0.851068340122, 0.851948647726, 0.852829615446, 0.853711244958, \
    0.854593537942, 0.855476496083, 0.856360121074, 0.857244414613, \
    0.858129378404, 0.859015014157, 0.859901323588, 0.860788308418, \
    0.861675970376, 0.862564311196, 0.863453332618, 0.864343036389, \
    0.865233424261, 0.866124497993, 0.86701625935, 0.867908710104, \
    0.868801852031, 0.869695686916, 0.870590216549, 0.871485442727, \
    0.872381367254, 0.873277991937, 0.874175318595, 0.875073349049, \
    0.875972085128, 0.876871528668, 0.877771681512, 0.878672545509, \
    0.879574122514, 0.88047641439, 0.881379423006, 0.882283150238, \
    0.883187597969, 0.884092768089, 0.884998662493, 0.885905283087, \
    0.886812631779, 0.887720710488, 0.888629521138, 0.889539065661, \
    0.890449345995, 0.891360364086, 0.892272121887, 0.893184621359, \
    0.894097864469, 0.895011853191, 0.895926589508, 0.896842075409, \
    0.897758312891, 0.898675303958, 0.899593050622, 0.900511554903, \
    0.901430818827, 0.902350844428, 0.90327163375, 0.90419318884, \
    0.905115511758, 0.906038604567, 0.906962469342, 0.907887108163, \
    0.908812523118, 0.909738716305, 0.910665689828, 0.911593445799, \
    0.912521986339, 0.913451313577, 0.91438142965, 0.915312336703, \
    0.916244036888, 0.917176532369, 0.918109825313, 0.919043917899, \
    0.919978812315, 0.920914510754, 0.921851015421, 0.922788328527, \
    0.923726452292, 0.924665388946, 0.925605140727, 0.926545709881, \
    0.927487098664, 0.928429309338, 0.929372344179, 0.930316205466, \
    0.931260895491, 0.932206416553, 0.933152770962, 0.934099961035, \
    0.9350479891, 0.935996857491, 0.936946568555, 0.937897124647, \
    0.93884852813, 0.939800781378, 0.940753886774, 0.941707846709, \
    0.942662663587, 0.943618339818, 0.944574877824, 0.945532280036, \
    0.946490548893, 0.947449686847, 0.948409696358, 0.949370579895, \
    0.95033233994, 0.951294978982, 0.952258499521, 0.953222904069, \
    0.954188195145, 0.955154375281, 0.956121447017, 0.957089412906, \
    0.958058275508, 0.959028037398, 0.959998701157, 0.960970269379, \
    0.961942744669, 0.962916129641, 0.963890426921, 0.964865639146, \
    0.965841768964, 0.966818819033, 0.967796792022, 0.968775690612, \
    0.969755517495, 0.970736275374, 0.971717966963, 0.972700594988, \
    0.973684162186, 0.974668671305, 0.975654125105, 0.976640526359, \
    0.977627877849, 0.978616182371, 0.979605442731, 0.980595661749, \
    0.981586842254, 0.982578987091, 0.983572099113, 0.984566181188, \
    0.985561236196, 0.986557267027, 0.987554276585, 0.988552267788, \
    0.989551243564, 0.990551206854, 0.991552160613, 0.992554107808, \
    0.993557051418, 0.994560994436, 0.995565939868, 0.996571890733, \
    0.997578850062, 0.9985868209, 0.999595806306, 1.00060580935, \
    1.00161683312, 1.00262888071, 1.00364195524, 1.00465605983, \
    1.00567119762, 1.00668737176, 1.00770458543, 1.0087228418, \
    1.00974214407, 1.01076249545, 1.01178389916, 1.01280635844, \
    1.01382987655, 1.01485445675, 1.01588010232, 1.01690681657, \
    1.01793460279, 1.01896346433, 1.01999340452, 1.02102442671, \
    1.02205653428, 1.02308973062, 1.02412401912, 1.02515940322, \
    1.02619588633, 1.02723347191, 1.02827216342, 1.02931196435, \
    1.03035287819, 1.03139490845, 1.03243805866, 1.03348233237, \
    1.03452773314, 1.03557426455, 1.03662193018, 1.03767073366, \
    1.03872067861, 1.03977176868, 1.04082400752, 1.04187739881, \
    1.04293194626, 1.04398765357, 1.04504452448, 1.04610256273, \
    1.04716177209, 1.04822215635, 1.04928371929, 1.05034646476, \
    1.05141039657, 1.0524755186, 1.0535418347, 1.05460934878, \
    1.05567806475, 1.05674798653, 1.05781911808, 1.05889146336, \
    1.05996502636, 1.06103981109, 1.06211582157, 1.06319306184, \
    1.06427153597, 1.06535124805, 1.06643220217, 1.06751440246, \
    1.06859785307, 1.06968255816, 1.07076852192, 1.07185574854, \
    1.07294424226, 1.07403400732, 1.07512504799, 1.07621736855, \
    1.07731097332, 1.07840586663, 1.07950205283, 1.0805995363, \
    1.08169832142, 1.08279841262, 1.08389981434, 1.08500253104, \
    1.08610656721, 1.08721192734, 1.08831861598, 1.08942663766, \
    1.09053599698, 1.09164669853, 1.09275874692, 1.09387214681, \
    1.09498690286, 1.09610301977, 1.09722050226, 1.09833935506, \
    1.09945958293, 1.10058119068, 1.10170418311, 1.10282856507, \
    1.10395434141, 1.10508151703, 1.10621009684, 1.10734008578, \
    1.10847148882, 1.10960431095, 1.11073855719, 1.11187423257, \
    1.11301134218, 1.11414989111, 1.11528988448, 1.11643132745, \
    1.11757422519, 1.1187185829, 1.11986440583, 1.12101169923, \
    1.12216046839, 1.12331071862, 1.12446245528, 1.12561568374, \
    1.1267704094, 1.12792663769, 1.12908437408, 1.13024362405, \
    1.13140439313, 1.13256668686, 1.13373051083, 1.13489587064, \
    1.13606277195, 1.13723122041, 1.13840122174, 1.13957278166, \
    1.14074590595, 1.14192060039, 1.14309687083, 1.14427472312, \
    1.14545416315, 1.14663519686, 1.1478178302, 1.14900206916, \
    1.15018791978, 1.1513753881, 1.15256448023, 1.1537552023, \
    1.15494756045, 1.1561415609, 1.15733720988, 1.15853451364, \
    1.1597334785, 1.16093411079, 1.16213641689, 1.16334040321, \
    1.1645460762, 1.16575344233, 1.16696250814, 1.16817328018, \
    1.16938576505, 1.17059996938, 1.17181589985, 1.17303356317, \
    1.17425296609, 1.1754741154, 1.17669701793, 1.17792168055, \
    1.17914811017, 1.18037631374, 1.18160629825, 1.18283807074, \
    1.18407163828, 1.18530700798, 1.18654418701, 1.18778318256, \
    1.18902400188, 1.19026665225, 1.19151114101, 1.19275747553, \
    1.19400566322, 1.19525571156, 1.19650762804, 1.19776142023, \
    1.19901709572, 1.20027466216, 1.20153412724, 1.2027954987, \
    1.20405878432, 1.20532399194, 1.20659112944, 1.20786020475, \
    1.20913122586, 1.21040420078, 1.21167913759, 1.21295604444, \
    1.21423492948, 1.21551580096, 1.21679866716, 1.2180835364, \
    1.21937041707, 1.22065931762, 1.22195024653, 1.22324321234, \
    1.22453822366, 1.22583528914, 1.22713441748, 1.22843561746, \
    1.22973889789, 1.23104426764, 1.23235173565, 1.23366131092, \
    1.23497300248, 1.23628681945, 1.23760277098, 1.23892086632, \
    1.24024111474, 1.24156352558, 1.24288810826, 1.24421487225, \
    1.24554382707, 1.24687498231, 1.24820834764, 1.24954393277, \
    1.25088174749, 1.25222180165, 1.25356410517, 1.25490866802, \
    1.25625550025, 1.25760461198, 1.25895601339, 1.26030971474, \
    1.26166572634, 1.26302405859, 1.26438472195, 1.26574772695, \
    1.26711308419, 1.26848080436, 1.2698508982, 1.27122337654, \
    1.27259825027, 1.27397553036, 1.27535522788, 1.27673735394, \
    1.27812191975, 1.27950893658, 1.2808984158, 1.28229036885, \
    1.28368480725, 1.2850817426, 1.28648118658, 1.28788315096, \
    1.28928764758, 1.29069468838, 1.29210428538, 1.29351645068, \
    1.29493119647, 1.29634853503, 1.29776847873, 1.29919104001, \
    1.30061623144, 1.30204406564, 1.30347455533, 1.30490771336, \
    1.30634355261, 1.30778208612, 1.30922332698, 1.31066728839, \
    1.31211398366, 1.31356342618, 1.31501562944, 1.31647060705, \
    1.3179283727, 1.31938894019, 1.32085232344, 1.32231853644, \
    1.32378759331, 1.32525950829, 1.32673429568, 1.32821196994, \
    1.3296925456, 1.33117603734, 1.33266245992, 1.33415182822, \
    1.33564415726, 1.33713946213, 1.33863775808, 1.34013906045, \
    1.34164338473, 1.34315074649, 1.34466116145, 1.34617464545, \
    1.34769121444, 1.34921088453, 1.35073367192, 1.35225959295, \
    1.3537886641, 1.35532090198, 1.35685632332, 1.35839494499, \
    1.35993678401, 1.36148185752, 1.3630301828, 1.36458177727, \
    1.36613665852, 1.36769484423, 1.36925635228, 1.37082120066, \
    1.37238940752, 1.37396099116, 1.37553597004, 1.37711436276, \
    1.37869618807, 1.3802814649, 1.38187021232, 1.38346244956, \
    1.38505819603, 1.38665747129, 1.38826029505, 1.38986668723, \
    1.39147666789, 1.39309025725, 1.39470747574, 1.39632834393, \
    1.3979528826, 1.39958111269, 1.40121305532, 1.40284873181, \
    1.40448816364, 1.40613137251, 1.40777838029, 1.40942920906, \
    1.41108388106, 1.41274241877, 1.41440484485, 1.41607118216, \
    1.41774145377, 1.41941568296, 1.42109389321, 1.42277610822, \
    1.42446235191, 1.4261526484, 1.42784702206, 1.42954549744, \
    1.43124809936, 1.43295485285, 1.43466578316, 1.43638091579, \
    1.43810027647, 1.43982389118, 1.44155178613, 1.44328398779, \
    1.44502052286, 1.44676141832, 1.44850670139, 1.45025639954, \
    1.45201054053, 1.45376915236, 1.4555322633, 1.45729990192, \
    1.45907209704, 1.46084887778, 1.46263027351, 1.46441631394, \
    1.46620702902, 1.46800244903, 1.46980260454, 1.47160752641, \
    1.47341724582, 1.47523179427, 1.47705120356, 1.47887550581, \
    1.48070473348, 1.48253891934, 1.48437809651, 1.48622229844, \
    1.48807155892, 1.48992591209, 1.49178539245, 1.49365003484, \
    1.49551987447, 1.49739494693, 1.49927528818, 1.50116093452, \
    1.50305192269, 1.50494828979, 1.5068500733, 1.50875731112, \
    1.51067004156, 1.51258830332, 1.51451213554, 1.51644157777, \
    1.51837667, 1.52031745264, 1.52226396655, 1.52421625305, \
    1.52617435391, 1.52813831134, 1.53010816806, 1.53208396723, \
    1.53406575252, 1.53605356807, 1.53804745854, 1.54004746908, \
    1.54205364536, 1.54406603357, 1.54608468043, 1.5481096332, \
    1.55014093969, 1.55217864825, 1.55422280782, 1.55627346789, \
    1.55833067854, 1.56039449044, 1.56246495486, 1.56454212368, \
    1.56662604942, 1.56871678519, 1.57081438477, 1.57291890258, \
    1.57503039371, 1.57714891392, 1.57927451964, 1.581407268, \
    1.58354721686, 1.58569442477, 1.58784895103, 1.59001085565, \
    1.59218019943, 1.59435704393, 1.59654145149, 1.59873348523, \
    1.60093320909, 1.60314068784, 1.60535598708, 1.60757917325, \
    1.60981031368, 1.61204947656, 1.61429673098, 1.61655214696, \
    1.61881579544, 1.62108774828, 1.62336807836, 1.62565685948, \
    1.62795416649, 1.63026007522, 1.63257466256, 1.63489800643, \
    1.63723018585, 1.63957128092, 1.64192137286, 1.64428054402, \
    1.64664887792, 1.64902645924, 1.65141337389, 1.65380970898, \
    1.65621555288, 1.65863099522, 1.66105612696, 1.66349104035, \
    1.665935829, 1.6683905879, 1.67085541345, 1.67333040348, \
    1.67581565725, 1.67831127556, 1.68081736069, 1.68333401649, \
    1.6858613484, 1.68839946345, 1.69094847035, 1.69350847947, \
    1.69607960292, 1.69866195455, 1.70125565, 1.70386080677, \
    1.70647754419, 1.70910598353, 1.71174624799, 1.7143984628, \
    1.71706275519, 1.71973925449, 1.72242809217, 1.72512940185, \
    1.72784331941, 1.73056998298, 1.73330953303, 1.7360621124, \
    1.73882786639, 1.74160694276, 1.74439949184, 1.74720566658, \
    1.75002562257, 1.75285951816, 1.75570751448, 1.75856977555, \
    1.7614464683, 1.7643377627, 1.76724383175, 1.77016485166, \
    1.77310100183, 1.77605246501, 1.77901942732, 1.78200207837, \
    1.78500061134, 1.78801522309, 1.79104611422, 1.79409348917, \
    1.79715755637, 1.80023852827, 1.8033366215, 1.80645205698, \
    1.80958506, 1.81273586036, 1.81590469249, 1.81909179558, \
    1.82229741372, 1.825521796, 1.82876519668, 1.83202787533, \
    1.83531009698, 1.83861213227, 1.84193425762, 1.84527675539, \
    1.84863991405, 1.85202402837, 1.8554293996, 1.85885633567, \
    1.86230515137, 1.86577616858, 1.86926971649, 1.87278613181, \
    1.87632575899, 1.8798889505, 1.88347606705, 1.88708747787, \
    1.89072356098, 1.89438470345, 1.89807130174, 1.90178376197, \
    1.90552250025, 1.90928794302, 1.91308052741, 1.91690070156, \
    1.92074892503, 1.92462566922, 1.92853141772, 1.93246666677, \
    1.93643192574, 1.94042771755, 1.94445457918, 1.9485130622, \
    1.95260373328, 1.95672717477, 1.96088398528, 1.96507478031, \
    1.96930019287, 1.97356087419, 1.97785749442, 1.98219074335, \
    1.98656133124, 1.99096998962, 1.99541747213, 1.99990455547, \
    2.00443204036, 2.00900075251, 2.01361154371, 2.01826529295, \
    2.02296290758, 2.02770532458, 2.03249351185, 2.03732846962, \
    2.04221123192, 2.0471428681, 2.05212448451, 2.05715722623, \
    2.06224227888, 2.06738087065, 2.07257427429, 2.07782380938, \
    2.08313084465, 2.08849680045, 2.09392315145, 2.09941142942, \
    2.10496322628, 2.11058019727, 2.11626406445, 2.12201662031, \
    2.12783973172, 2.13373534416, 2.13970548619, 2.14575227431, \
    2.15187791816, 2.1580847261, 2.16437511125, 2.17075159793, \
    2.17721682871, 2.18377357191, 2.19042472984, 2.1971733476, \
    2.20402262267, 2.21097591537, 2.21803676019, 2.22520887808, \
    2.23249618993, 2.23990283128, 2.24743316835, 2.25509181569, \
    2.26288365549, 2.27081385882, 2.27888790909, 2.28711162784, \
    2.29549120334, 2.30403322228, 2.31274470495, 2.32163314439, \
    2.33070655011, 2.33997349698, 2.34944318006, 2.35912547628, \
    2.36903101398, 2.37917125159, 2.3895585669, 2.40020635872, \
    2.411129163, 2.422342786, 2.43386445755, 2.44571300825, \
    2.45790907518, 2.47047534177, 2.48343681896, 2.49682117646, \
    2.51065913523, 2.52498493519, 2.53983689632, 2.55525809634, \
    2.57129719532, 2.58800944712, 2.60545795099, 2.62371521493, \
    2.64286512889, 2.66300548366, 2.68425122698, 2.7067387311, \
    2.73063147325, 2.75612772826, 2.78347119119, 2.81296597401, \
    2.84499832124, 2.8800689917, 2.91884323355, 2.9622311235, \
    3.0115232357, 3.06863405379, 3.13657337257, 3.22045475765, \
    3.32996541598, 3.48672170399 ])

yu = array([
    0.0540012735356, 0.0544874991381, 0.054972661389, 0.0554567692269, \
    0.0559398314244, 0.0564218565922, 0.0569028531841, 0.0573828295011, \
    0.0578617936955, 0.0583397537752, 0.058816717607, 0.059292692921, \
    0.0597676873138, 0.060241708252, 0.0607147630756, 0.0611868590013, \
    0.0616580031256, 0.0621282024276, 0.0625974637723, 0.0630657939132, \
    0.0635331994951, 0.0639996870564, 0.0644652630325, 0.0649299337573, \
    0.0653937054663, 0.0658565842984, 0.0663185762986, 0.0667796874201, \
    0.0672399235259, 0.0676992903918, 0.0681577937072, 0.0686154390782, \
    0.0690722320286, 0.0695281780022, 0.0699832823643, 0.0704375504035, \
    0.0708909873334, 0.0713435982942, 0.0717953883543, 0.0722463625114, \
    0.0726965256949, 0.0731458827663, 0.0735944385211, 0.0740421976905, \
    0.074489164942, 0.0749353448811, 0.0753807420524, 0.0758253609412, \
    0.076269205974, 0.0767122815202, 0.0771545918932, 0.077596141351, \
    0.0780369340979, 0.0784769742851, 0.078916266012, 0.0793548133268, \
    0.0797926202279, 0.0802296906646, 0.080666028538, 0.081101637702, \
    0.081536521964, 0.0819706850859, 0.082404130785, 0.0828368627345, \
    0.0832688845646, 0.0837001998631, 0.0841308121761, 0.084560725009, \
    0.0849899418268, 0.0854184660553, 0.0858463010813, 0.0862734502535, \
    0.0866999168832, 0.0871257042449, 0.0875508155769, 0.0879752540816, \
    0.0883990229268, 0.0888221252457, 0.0892445641375, 0.0896663426683, \
    0.0900874638713, 0.0905079307475, 0.0909277462662, 0.0913469133655, \
    0.0917654349529, 0.0921833139053, 0.0926005530704, 0.0930171552661, \
    0.0934331232819, 0.0938484598786, 0.0942631677893, 0.0946772497194, \
    0.0950907083474, 0.095503546325, 0.0959157662776, 0.0963273708049, \
    0.0967383624809, 0.0971487438546, 0.0975585174503, 0.0979676857678, \
    0.098376251283, 0.098784216448, 0.0991915836918, 0.0995983554201, \
    0.100004534016, 0.100410121841, 0.100815121233, 0.10121953451, \
    0.101623363968, 0.102026611881, 0.102429280502, 0.102831372066, \
    0.103232888785, 0.103633832853, 0.104034206444, 0.10443401171, \
    0.104833250787, 0.105231925791, 0.10563003882, 0.106027591953, \
    0.106424587249, 0.106821026753, 0.10721691249, 0.107612246467, \
    0.108007030675, 0.108401267088, 0.108794957663, 0.10918810434, \
    0.109580709043, 0.109972773679, 0.110364300142, 0.110755290307, \
    0.111145746034, 0.111535669171, 0.111925061545, 0.112313924974, \
    0.112702261257, 0.113090072181, 0.113477359516, 0.113864125022, \
    0.11425037044, 0.1146360975, 0.115021307918, 0.115406003396, \
    0.115790185624, 0.116173856276, 0.116557017014, 0.11693966949, \
    0.117321815339, 0.117703456185, 0.118084593641, 0.118465229306, \
    0.118845364768, 0.1192250016, 0.119604141367, 0.119982785621, \
    0.120360935901, 0.120738593735, 0.121115760642, 0.121492438126, \
    0.121868627682, 0.122244330795, 0.122619548937, 0.12299428357, \
    0.123368536146, 0.123742308106, 0.124115600881, 0.12448841589, \
    0.124860754545, 0.125232618245, 0.12560400838, 0.125974926331, \
    0.126345373469, 0.126715351154, 0.127084860738, 0.127453903564, \
    0.127822480963, 0.128190594259, 0.128558244767, 0.128925433793, \
    0.129292162631, 0.129658432571, 0.130024244891, 0.13038960086, \
    0.130754501741, 0.131118948787, 0.131482943242, 0.131846486342, \
    0.132209579317, 0.132572223385, 0.132934419758, 0.133296169642, \
    0.13365747423, 0.134018334713, 0.13437875227, 0.134738728074, \
    0.13509826329, 0.135457359075, 0.135816016581, 0.13617423695, \
    0.136532021316, 0.13688937081, 0.137246286551, 0.137602769653, \
    0.137958821225, 0.138314442365, 0.138669634167, 0.139024397717, \
    0.139378734095, 0.139732644373, 0.140086129618, 0.14043919089, \
    0.140791829241, 0.141144045718, 0.141495841361, 0.141847217205, \
    0.142198174276, 0.142548713597, 0.142898836183, 0.143248543043, \
    0.143597835179, 0.14394671359, 0.144295179266, 0.144643233193, \
    0.144990876349, 0.14533810971, 0.145684934242, 0.146031350908, \
    0.146377360665, 0.146722964463, 0.147068163249, 0.147412957962, \
    0.147757349537, 0.148101338903, 0.148444926984, 0.148788114699, \
    0.149130902961, 0.149473292678, 0.149815284753, 0.150156880085, \
    0.150498079565, 0.150838884082, 0.151179294519, 0.151519311753, \
    0.151858936658, 0.152198170101, 0.152537012946, 0.152875466051, \
    0.153213530271, 0.153551206454, 0.153888495445, 0.154225398084, \
    0.154561915205, 0.15489804764, 0.155233796214, 0.155569161751, \
    0.155904145066, 0.156238746972, 0.156572968279, 0.156906809791, \
    0.157240272307, 0.157573356623, 0.15790606353, 0.158238393817, \
    0.158570348265, 0.158901927654, 0.159233132759, 0.159563964351, \
    0.159894423197, 0.160224510058, 0.160554225695, 0.160883570863, \
    0.161212546311, 0.161541152788, 0.161869391036, 0.162197261796, \
    0.162524765803, 0.162851903789, 0.163178676483, 0.163505084608, \
    0.163831128886, 0.164156810034, 0.164482128766, 0.164807085792, \
    0.165131681818, 0.165455917548, 0.165779793681, 0.166103310913, \
    0.166426469936, 0.16674927144, 0.167071716111, 0.167393804631, \
    0.167715537679, 0.16803691593, 0.168357940058, 0.168678610731, \
    0.168998928615, 0.169318894373, 0.169638508664, 0.169957772145, \
    0.170276685469, 0.170595249286, 0.170913464242, 0.171231330982, \
    0.171548850146, 0.171866022373, 0.172182848295, 0.172499328546, \
    0.172815463755, 0.173131254545, 0.173446701542, 0.173761805364, \
    0.174076566628, 0.174390985949, 0.174705063937, 0.175018801202, \
    0.175332198348, 0.175645255979, 0.175957974695, 0.176270355092, \
    0.176582397766, 0.176894103309, 0.177205472308, 0.177516505351, \
    0.177827203022, 0.178137565902, 0.178447594568, 0.178757289598, \
    0.179066651564, 0.179375681037, 0.179684378585, 0.179992744774, \
    0.180300780166, 0.180608485323, 0.180915860803, 0.18122290716, \
    0.181529624949, 0.18183601472, 0.182142077022, 0.182447812399, \
    0.182753221396, 0.183058304554, 0.183363062412, 0.183667495505, \
    0.183971604368, 0.184275389534, 0.18457885153, 0.184881990885, \
    0.185184808123, 0.185487303768, 0.185789478338, 0.186091332353, \
    0.186392866329, 0.186694080779, 0.186994976215, 0.187295553146, \
    0.18759581208, 0.187895753521, 0.188195377973, 0.188494685937, \
    0.188793677911, 0.189092354391, 0.189390715873, 0.18968876285, \
    0.189986495811, 0.190283915244, 0.190581021638, 0.190877815475, \
    0.191174297238, 0.191470467408, 0.191766326463, 0.192061874879, \
    0.192357113132, 0.192652041693, 0.192946661033, 0.193240971621, \
    0.193534973925, 0.193828668408, 0.194122055533, 0.194415135763, \
    0.194707909556, 0.19500037737, 0.195292539661, 0.195584396882, \
    0.195875949485, 0.196167197921, 0.196458142637, 0.196748784081, \
    0.197039122697, 0.197329158929, 0.197618893218, 0.197908326003, \
    0.198197457722, 0.198486288812, 0.198774819706, 0.199063050838, \
    0.199350982639, 0.199638615537, 0.199925949961, 0.200212986337, \
    0.200499725089, 0.20078616664, 0.20107231141, 0.20135815982, \
    0.201643712287, 0.201928969228, 0.202213931056, 0.202498598186, \
    0.202782971029, 0.203067049994, 0.20335083549, 0.203634327924, \
    0.203917527701, 0.204200435225, 0.204483050898, 0.204765375121, \
    0.205047408293, 0.205329150811, 0.205610603072, 0.205891765471, \
    0.2061726384, 0.206453222252, 0.206733517417, 0.207013524284, \
    0.207293243239, 0.20757267467, 0.207851818961, 0.208130676495, \
    0.208409247653, 0.208687532816, 0.208965532363, 0.209243246671, \
    0.209520676117, 0.209797821075, 0.210074681919, 0.210351259021, \
    0.210627552752, 0.21090356348, 0.211179291575, 0.211454737402, \
    0.211729901327, 0.212004783714, 0.212279384926, 0.212553705325, \
    0.21282774527, 0.213101505121, 0.213374985234, 0.213648185967, \
    0.213921107674, 0.214193750709, 0.214466115425, 0.214738202173, \
    0.215010011303, 0.215281543164, 0.215552798104, 0.215823776468, \
    0.216094478602, 0.21636490485, 0.216635055555, 0.216904931057, \
    0.217174531699, 0.217443857818, 0.217712909752, 0.21798168784, \
    0.218250192415, 0.218518423813, 0.218786382367, 0.219054068409, \
    0.21932148227, 0.21958862428, 0.219855494768, 0.220122094062, \
    0.220388422488, 0.220654480371, 0.220920268035, 0.221185785805, \
    0.221451034002, 0.221716012947, 0.22198072296, 0.222245164359, \
    0.222509337463, 0.222773242589, 0.223036880051, 0.223300250165, \
    0.223563353244, 0.2238261896, 0.224088759545, 0.224351063389, \
    0.224613101442, 0.224874874012, 0.225136381406, 0.22539762393, \
    0.22565860189, 0.22591931559, 0.226179765333, 0.226439951422, \
    0.226699874157, 0.22695953384, 0.227218930768, 0.227478065241, \
    0.227736937556, 0.227995548009, 0.228253896895, 0.22851198451, \
    0.228769811145, 0.229027377095, 0.22928468265, 0.229541728101, \
    0.229798513738, 0.23005503985, 0.230311306723, 0.230567314646, \
    0.230823063904, 0.231078554782, 0.231333787564, 0.231588762534, \
    0.231843479974, 0.232097940164, 0.232352143387, 0.232606089921, \
    0.232859780045, 0.233113214036, 0.233366392173, 0.233619314731, \
    0.233871981984, 0.234124394209, 0.234376551677, 0.234628454662, \
    0.234880103436, 0.235131498268, 0.235382639431, 0.235633527192, \
    0.23588416182, 0.236134543582, 0.236384672746, 0.236634549577, \
    0.23688417434, 0.2371335473, 0.237382668719, 0.237631538861, \
    0.237880157987, 0.238128526359, 0.238376644236, 0.238624511878, \
    0.238872129544, 0.23911949749, 0.239366615975, 0.239613485254, \
    0.239860105583, 0.240106477217, 0.240352600409, 0.240598475413, \
    0.240844102481, 0.241089481863, 0.241334613813, 0.241579498578, \
    0.241824136409, 0.242068527555, 0.242312672262, 0.242556570778, \
    0.24280022335, 0.243043630222, 0.243286791641, 0.243529707849, \
    0.24377237909, 0.244014805607, 0.244256987642, 0.244498925435, \
    0.244740619229, 0.244982069261, 0.245223275772, 0.245464238999, \
    0.24570495918, 0.245945436553, 0.246185671353, 0.246425663816, \
    0.246665414177, 0.24690492267, 0.247144189529, 0.247383214985, \
    0.247621999273, 0.247860542621, 0.248098845263, 0.248336907427, \
    0.248574729343, 0.24881231124, 0.249049653346, 0.249286755888, \
    0.249523619094, 0.249760243188, 0.249996628397, 0.250232774945, \
    0.250468683057, 0.250704352956, 0.250939784865, 0.251174979007, \
    0.251409935601, 0.251644654871, 0.251879137035, 0.252113382314, \
    0.252347390927, 0.252581163092, 0.252814699027, 0.253047998949, \
    0.253281063075, 0.253513891621, 0.253746484801, 0.253978842831, \
    0.254210965925, 0.254442854297, 0.254674508159, 0.254905927723, \
    0.255137113202, 0.255368064807, 0.255598782747, 0.255829267233, \
    0.256059518475, 0.256289536681, 0.256519322059, 0.256748874817, \
    0.256978195162, 0.2572072833, 0.257436139437, 0.257664763779, \
    0.25789315653, 0.258121317895, 0.258349248077, 0.258576947278, \
    0.258804415703, 0.259031653551, 0.259258661026, 0.259485438327, \
    0.259711985655, 0.259938303209, 0.260164391189, 0.260390249794, \
    0.260615879221, 0.260841279668, 0.261066451331, 0.261291394408, \
    0.261516109095, 0.261740595585, 0.261964854076, 0.26218888476, \
    0.262412687831, 0.262636263484, 0.26285961191, 0.263082733302, \
    0.263305627851, 0.263528295749, 0.263750737186, 0.263972952353, \
    0.264194941439, 0.264416704633, 0.264638242124, 0.2648595541, \
    0.265080640748, 0.265301502256, 0.265522138811, 0.265742550598, \
    0.265962737803, 0.266182700611, 0.266402439207, 0.266621953774, \
    0.266841244498, 0.26706031156, 0.267279155143, 0.26749777543, \
    0.267716172603, 0.267934346842, 0.268152298328, 0.268370027242, \
    0.268587533763, 0.268804818071, 0.269021880344, 0.269238720761, \
    0.2694553395, 0.269671736739, 0.269887912653, 0.270103867421, \
    0.270319601217, 0.270535114218, 0.270750406598, 0.270965478533, \
    0.271180330196, 0.271394961762, 0.271609373403, 0.271823565293, \
    0.272037537604, 0.272251290507, 0.272464824175, 0.272678138779, \
    0.272891234489, 0.273104111476, 0.273316769908, 0.273529209956, \
    0.273741431789, 0.273953435575, 0.274165221481, 0.274376789677, \
    0.274588140328, 0.274799273601, 0.275010189664, 0.275220888681, \
    0.275431370818, 0.275641636241, 0.275851685114, 0.2760615176, \
    0.276271133865, 0.276480534071, 0.276689718381, 0.276898686958, \
    0.277107439965, 0.277315977561, 0.27752429991, 0.277732407172, \
    0.277940299507, 0.278147977076, 0.278355440038, 0.278562688553, \
    0.278769722779, 0.278976542875, 0.279183149, 0.27938954131, \
    0.279595719963, 0.279801685116, 0.280007436926, 0.280212975549, \
    0.280418301139, 0.280623413854, 0.280828313848, 0.281033001275, \
    0.281237476289, 0.281441739045, 0.281645789695, 0.281849628394, \
    0.282053255293, 0.282256670545, 0.282459874302, 0.282662866715, \
    0.282865647935, 0.283068218114, 0.283270577402, 0.283472725948, \
    0.283674663903, 0.283876391415, 0.284077908635, 0.284279215709, \
    0.284480312788, 0.284681200017, 0.284881877546, 0.285082345521, \
    0.285282604088, 0.285482653395, 0.285682493588, 0.285882124811, \
    0.286081547211, 0.286280760932, 0.286479766119, 0.286678562916, \
    0.286877151468, 0.287075531918, 0.287273704409, 0.287471669084, \
    0.287669426085, 0.287866975555, 0.288064317636, 0.28826145247, \
    0.288458380196, 0.288655100957, 0.288851614893, 0.289047922144, \
    0.289244022849, 0.289439917148, 0.289635605182, 0.289831087087, \
    0.290026363003, 0.290221433068, 0.290416297419, 0.290610956195, \
    0.290805409533, 0.290999657568, 0.291193700439, 0.29138753828, \
    0.291581171228, 0.291774599419, 0.291967822987, 0.292160842068, \
    0.292353656796, 0.292546267306, 0.292738673731, 0.292930876204, \
    0.29312287486, 0.293314669832, 0.293506261251, 0.293697649251, \
    0.293888833963, 0.294079815519, 0.294270594051, 0.29446116969, \
    0.294651542566, 0.294841712811, 0.295031680553, 0.295221445924, \
    0.295411009053, 0.295600370069, 0.295789529101, 0.295978486277, \
    0.296167241727, 0.296355795578, 0.296544147958, 0.296732298995, \
    0.296920248815, 0.297107997546, 0.297295545315, 0.297482892246, \
    0.297670038468, 0.297856984104, 0.298043729282, 0.298230274125, \
    0.298416618759, 0.298602763308, 0.298788707897, 0.298974452649, \
    0.299159997689, 0.299345343139, 0.299530489123, 0.299715435764, \
    0.299900183184, 0.300084731505, 0.30026908085, 0.300453231339, \
    0.300637183096, 0.30082093624, 0.301004490893, 0.301187847175, \
    0.301371005207, 0.301553965108, 0.301736726999, 0.301919290999, \
    0.302101657227, 0.302283825802, 0.302465796843, 0.302647570468, \
    0.302829146795, 0.303010525942, 0.303191708028, 0.303372693168, \
    0.303553481481, 0.303734073083, 0.30391446809, 0.304094666619, \
    0.304274668786, 0.304454474707, 0.304634084497, 0.304813498271, \
    0.304992716144, 0.305171738232, 0.305350564647, 0.305529195506, \
    0.305707630921, 0.305885871006, 0.306063915875, 0.306241765641, \
    0.306419420416, 0.306596880314, 0.306774145446, 0.306951215926, \
    0.307128091864, 0.307304773373, 0.307481260563, 0.307657553547, \
    0.307833652434, 0.308009557336, 0.308185268362, 0.308360785624, \
    0.308536109231, 0.308711239292, 0.308886175918, 0.309060919216, \
    0.309235469297, 0.309409826268, 0.309583990239, 0.309757961317, \
    0.309931739611, 0.310105325228, 0.310278718275, 0.31045191886, \
    0.31062492709, 0.310797743071, 0.310970366911, 0.311142798715, \
    0.31131503859, 0.31148708664, 0.311658942973, 0.311830607693, \
    0.312002080905, 0.312173362715, 0.312344453226, 0.312515352544, \
    0.312686060772, 0.312856578014, 0.313026904375, 0.313197039958, \
    0.313366984865, 0.313536739201, 0.313706303067, 0.313875676567, \
    0.314044859803, 0.314213852877, 0.31438265589, 0.314551268945, \
    0.314719692144, 0.314887925586, 0.315055969374, 0.315223823609, \
    0.31539148839, 0.315558963818, 0.315726249993, 0.315893347016, \
    0.316060254985, 0.316226974001, 0.316393504163, 0.31655984557, \
    0.31672599832, 0.316891962512, 0.317057738245, 0.317223325617, \
    0.317388724726, 0.31755393567, 0.317718958546, 0.317883793451, \
    0.318048440483, 0.318212899739, 0.318377171315, 0.318541255307, \
    0.318705151813, 0.318868860929, 0.319032382749, 0.31919571737, \
    0.319358864888, 0.319521825397, 0.319684598993, 0.31984718577, \
    0.320009585823, 0.320171799247, 0.320333826135, 0.320495666583, \
    0.320657320683, 0.320818788529, 0.320980070215, 0.321141165834, \
    0.321302075479, 0.321462799242, 0.321623337217, 0.321783689496, \
    0.321943856171, 0.322103837334, 0.322263633077, 0.322423243491, \
    0.322582668669, 0.322741908701, 0.322900963677, 0.323059833691, \
    0.323218518831, 0.323377019188, 0.323535334852, 0.323693465915, \
    0.323851412464, 0.324009174591, 0.324166752385, 0.324324145934, \
    0.324481355329, 0.324638380658, 0.324795222009, 0.324951879472, \
    0.325108353134, 0.325264643085, 0.325420749411, 0.3255766722, \
    0.325732411541, 0.325887967521, 0.326043340226, 0.326198529745, \
    0.326353536163, 0.326508359567, 0.326663000045, 0.326817457682, \
    0.326971732564, 0.327125824778, 0.327279734408, 0.327433461542, \
    0.327587006263, 0.327740368658, 0.327893548812, 0.328046546808, \
    0.328199362732, 0.328351996669, 0.328504448702, 0.328656718917, \
    0.328808807396, 0.328960714223, 0.329112439483, 0.329263983259, \
    0.329415345633, 0.32956652669, 0.329717526511, 0.32986834518, \
    0.330018982779, 0.330169439391, 0.330319715097, 0.33046980998, \
    0.330619724122, 0.330769457604, 0.330919010508, 0.331068382916, \
    0.331217574907, 0.331366586564, 0.331515417967, 0.331664069197, \
    0.331812540334, 0.331960831459, 0.332108942652, 0.332256873993, \
    0.332404625561, 0.332552197437, 0.332699589699, 0.332846802427, \
    0.332993835701, 0.333140689599, 0.3332873642, 0.333433859582, \
    0.333580175825, 0.333726313006, 0.333872271204, 0.334018050496, \
    0.334163650961, 0.334309072676, 0.334454315719, 0.334599380166, \
    0.334744266096, 0.334888973585, 0.33503350271, 0.335177853547, \
    0.335322026174, 0.335466020667, 0.335609837101, 0.335753475553, \
    0.335896936099, 0.336040218815, 0.336183323776, 0.336326251057, \
    0.336469000734, 0.336611572882, 0.336753967576, 0.336896184891, \
    0.3370382249, 0.33718008768, 0.337321773304, 0.337463281846, \
    0.33760461338, 0.337745767981, 0.337886745721, 0.338027546675, \
    0.338168170916, 0.338308618517, 0.33844888955, 0.338588984091, \
    0.33872890221, 0.33886864398, 0.339008209475, 0.339147598766, \
    0.339286811925, 0.339425849025, 0.339564710138, 0.339703395335, \
    0.339841904688, 0.339980238268, 0.340118396147, 0.340256378395, \
    0.340394185084, 0.340531816284, 0.340669272067, 0.340806552503, \
    0.340943657662, 0.341080587614, 0.34121734243, 0.341353922179, \
    0.341490326932, 0.341626556758, 0.341762611726, 0.341898491907, \
    0.342034197368, 0.34216972818, 0.342305084412, 0.342440266131, \
    0.342575273407, 0.342710106308, 0.342844764904, 0.342979249261, \
    0.343113559448, 0.343247695533, 0.343381657583, 0.343515445668, \
    0.343649059853, 0.343782500207, 0.343915766796, 0.344048859689, \
    0.344181778951, 0.344314524649, 0.344447096851, 0.344579495623, \
    0.344711721031, 0.344843773142, 0.344975652022, 0.345107357736, \
    0.345238890351, 0.345370249932, 0.345501436546, 0.345632450257, \
    0.34576329113, 0.345893959232, 0.346024454627, 0.346154777379, \
    0.346284927555, 0.346414905218, 0.346544710432, 0.346674343264, \
    0.346803803775, 0.346933092032, 0.347062208097, 0.347191152035, \
    0.347319923909, 0.347448523782, 0.34757695172, 0.347705207784, \
    0.347833292037, 0.347961204544, 0.348088945366, 0.348216514568, \
    0.34834391221, 0.348471138357, 0.348598193069, 0.348725076411, \
    0.348851788443, 0.348978329228, 0.349104698827, 0.349230897303, \
    0.349356924717, 0.349482781131, 0.349608466606, 0.349733981203, \
    0.349859324983, 0.349984498007, 0.350109500337, 0.350234332033, \
    0.350358993156, 0.350483483765, 0.350607803923, 0.350731953687, \
    0.35085593312, 0.350979742281, 0.351103381229, 0.351226850025, \
    0.351350148728, 0.351473277398, 0.351596236094, 0.351719024875, \
    0.3518416438, 0.351964092929, 0.35208637232, 0.352208482032, \
    0.352330422124, 0.352452192653, 0.35257379368, 0.352695225262, \
    0.352816487456, 0.352937580322, 0.353058503916, 0.353179258297, \
    0.353299843523, 0.353420259651, 0.353540506738, 0.353660584842, \
    0.35378049402, 0.353900234329, 0.354019805826, 0.354139208567, \
    0.35425844261, 0.354377508012, 0.354496404828, 0.354615133114, \
    0.354733692928, 0.354852084326, 0.354970307363, 0.355088362094, \
    0.355206248577, 0.355323966867, 0.355441517019, 0.355558899089, \
    0.355676113131, 0.355793159202, 0.355910037356, 0.356026747648, \
    0.356143290133, 0.356259664866, 0.356375871902, 0.356491911294, \
    0.356607783098, 0.356723487367, 0.356839024156, 0.356954393519, \
    0.35706959551, 0.357184630183, 0.35729949759, 0.357414197787, \
    0.357528730826, 0.357643096761, 0.357757295645, 0.357871327531, \
    0.357985192472, 0.358098890522, 0.358212421732, 0.358325786157, \
    0.358438983847, 0.358552014857, 0.358664879237, 0.358777577041, \
    0.358890108321, 0.359002473128, 0.359114671515, 0.359226703533, \
    0.359338569235, 0.359450268671, 0.359561801893, 0.359673168954, \
    0.359784369903, 0.359895404792, 0.360006273672, 0.360116976594, \
    0.36022751361, 0.360337884769, 0.360448090122, 0.360558129721, \
    0.360668003615, 0.360777711854, 0.360887254489, 0.360996631571, \
    0.361105843148, 0.361214889271, 0.36132376999, 0.361432485354, \
    0.361541035413, 0.361649420216, 0.361757639813, 0.361865694253, \
    0.361973583586, 0.362081307859, 0.362188867123, 0.362296261425, \
    0.362403490816, 0.362510555343, 0.362617455054, 0.36272419, \
    0.362830760226, 0.362937165783, 0.363043406718, 0.363149483079, \
    0.363255394914, 0.36336114227, 0.363466725196, 0.36357214374, \
    0.363677397947, 0.363782487867, 0.363887413546, 0.363992175032, \
    0.364096772372, 0.364201205612, 0.364305474799, 0.364409579981, \
    0.364513521204, 0.364617298515, 0.364720911959, 0.364824361585, \
    0.364927647437, 0.365030769562, 0.365133728007, 0.365236522816, \
    0.365339154037, 0.365441621714, 0.365543925894, 0.365646066623, \
    0.365748043945, 0.365849857906, 0.365951508551, 0.366052995927, \
    0.366154320077, 0.366255481046, 0.366356478881, 0.366457313625, \
    0.366557985323, 0.36665849402, 0.366758839761, 0.366859022589, \
    0.36695904255, 0.367058899687, 0.367158594044, 0.367258125667, \
    0.367357494598, 0.367456700881, 0.367555744561, 0.36765462568, \
    0.367753344284, 0.367851900414, 0.367950294114, 0.368048525428, \
    0.368146594399, 0.36824450107, 0.368342245484, 0.368439827684, \
    0.368537247713, 0.368634505613, 0.368731601427, 0.368828535197, \
    0.368925306967, 0.369021916778, 0.369118364673, 0.369214650693, \
    0.369310774882, 0.36940673728, 0.36950253793, 0.369598176874, \
    0.369693654153, 0.369788969809, 0.369884123883, 0.369979116417, \
    0.370073947452, 0.37016861703, 0.370263125191, 0.370357471977, \
    0.370451657429, 0.370545681587, 0.370639544492, 0.370733246185, \
    0.370826786707, 0.370920166098, 0.371013384399, 0.371106441649, \
    0.37119933789, 0.371292073161, 0.371384647502, 0.371477060953, \
    0.371569313555, 0.371661405347, 0.371753336368, 0.371845106659, \
    0.371936716259, 0.372028165207, 0.372119453543, 0.372210581305, \
    0.372301548534, 0.372392355268, 0.372483001547, 0.372573487408, \
    0.372663812892, 0.372753978036, 0.372843982879, 0.372933827461, \
    0.373023511819, 0.373113035991, 0.373202400017, 0.373291603934, \
    0.373380647781, 0.373469531595, 0.373558255414, 0.373646819277, \
    0.373735223221, 0.373823467284, 0.373911551503, 0.373999475916, \
    0.37408724056, 0.374174845473, 0.374262290692, 0.374349576255, \
    0.374436702197, 0.374523668557, 0.374610475371, 0.374697122676, \
    0.374783610509, 0.374869938907, 0.374956107906, 0.375042117542, \
    0.375127967852, 0.375213658872, 0.37529919064, 0.375384563189, \
    0.375469776558, 0.375554830782, 0.375639725896, 0.375724461937, \
    0.37580903894, 0.375893456941, 0.375977715976, 0.37606181608, \
    0.376145757289, 0.376229539637, 0.37631316316, 0.376396627894, \
    0.376479933873, 0.376563081133, 0.376646069707, 0.376728899632, \
    0.376811570942, 0.376894083671, 0.376976437854, 0.377058633526, \
    0.377140670721, 0.377222549474, 0.377304269818, 0.377385831788, \
    0.377467235419, 0.377548480743, 0.377629567795, 0.377710496609, \
    0.377791267219, 0.377871879658, 0.37795233396, 0.378032630158, \
    0.378112768286, 0.378192748378, 0.378272570466, 0.378352234585, \
    0.378431740766, 0.378511089043, 0.378590279449, 0.378669312017, \
    0.37874818678, 0.378826903771, 0.378905463021, 0.378983864565, \
    0.379062108433, 0.37914019466, 0.379218123276, 0.379295894315, \
    0.379373507808, 0.379450963788, 0.379528262286, 0.379605403335, \
    0.379682386967, 0.379759213212, 0.379835882104, 0.379912393674, \
    0.379988747952, 0.380064944972, 0.380140984763, 0.380216867358, \
    0.380292592787, 0.380368161083, 0.380443572275, 0.380518826396, \
    0.380593923475, 0.380668863545, 0.380743646634, 0.380818272776, \
    0.380892741999, 0.380967054335, 0.381041209813, 0.381115208466, \
    0.381189050322, 0.381262735412, 0.381336263766, 0.381409635414, \
    0.381482850387, 0.381555908715, 0.381628810426, 0.381701555551, \
    0.381774144121, 0.381846576163, 0.381918851709, 0.381990970787, \
    0.382062933426, 0.382134739657, 0.382206389509, 0.38227788301, \
    0.382349220191, 0.382420401079, 0.382491425704, 0.382562294094, \
    0.38263300628, 0.382703562288, 0.382773962149, 0.382844205891, \
    0.382914293541, 0.382984225129, 0.383054000684, 0.383123620232, \
    0.383193083804, 0.383262391426, 0.383331543127, 0.383400538934, \
    0.383469378877, 0.383538062982, 0.383606591278, 0.383674963791, \
    0.383743180551, 0.383811241584, 0.383879146918, 0.383946896581, \
    0.384014490599, 0.384081929, 0.384149211811, 0.38421633906, \
    0.384283310773, 0.384350126978, 0.384416787701, 0.384483292969, \
    0.384549642809, 0.384615837248, 0.384681876312, 0.384747760028, \
    0.384813488423, 0.384879061522, 0.384944479352, 0.38500974194, \
    0.385074849312, 0.385139801493, 0.38520459851, 0.385269240389, \
    0.385333727156, 0.385398058837, 0.385462235457, 0.385526257042, \
    0.385590123617, 0.385653835209, 0.385717391843, 0.385780793545, \
    0.385844040338, 0.38590713225, 0.385970069305, 0.386032851528, \
    0.386095478944, 0.386157951579, 0.386220269457, 0.386282432603, \
    0.386344441042, 0.386406294798, 0.386467993897, 0.386529538363, \
    0.386590928221, 0.386652163494, 0.386713244207, 0.386774170385, \
    0.386834942052, 0.386895559231, 0.386956021948, 0.387016330226, \
    0.387076484089, 0.387136483561, 0.387196328665, 0.387256019426, \
    0.387315555867, 0.387374938013, 0.387434165885, 0.387493239508, \
    0.387552158906, 0.387610924101, 0.387669535118, 0.387727991978, \
    0.387786294705, 0.387844443323, 0.387902437854, 0.387960278321, \
    0.388017964748, 0.388075497156, 0.388132875569, 0.38819010001, \
    0.3882471705, 0.388304087062, 0.38836084972, 0.388417458495, \
    0.388473913409, 0.388530214485, 0.388586361746, 0.388642355212, \
    0.388698194907, 0.388753880852, 0.388809413069, 0.38886479158, \
    0.388920016407, 0.388975087572, 0.389030005096, 0.389084769, \
    0.389139379307, 0.389193836037, 0.389248139213, 0.389302288855, \
    0.389356284985, 0.389410127623, 0.389463816792, 0.389517352512, \
    0.389570734804, 0.389623963688, 0.389677039187, 0.38972996132, \
    0.389782730109, 0.389835345574, 0.389887807735, 0.389940116614, \
    0.38999227223, 0.390044274604, 0.390096123756, 0.390147819707, \
    0.390199362477, 0.390250752086, 0.390301988554, 0.390353071901, \
    0.390404002147, 0.390454779312, 0.390505403415, 0.390555874477, \
    0.390606192517, 0.390656357554, 0.390706369609, 0.390756228701, \
    0.390805934848, 0.390855488072, 0.39090488839, 0.390954135822, \
    0.391003230387, 0.391052172104, 0.391100960993, 0.391149597072, \
    0.391198080361, 0.391246410877, 0.39129458864, 0.391342613669, \
    0.391390485981, 0.391438205597, 0.391485772534, 0.39153318681, \
    0.391580448445, 0.391627557456, 0.391674513861, 0.39172131768, \
    0.39176796893, 0.391814467628, 0.391860813794, 0.391907007445, \
    0.391953048599, 0.391998937274, 0.392044673487, 0.392090257256, \
    0.392135688599, 0.392180967534, 0.392226094077, 0.392271068247, \
    0.392315890061, 0.392360559535, 0.392405076688, 0.392449441536, \
    0.392493654097, 0.392537714388, 0.392581622425, 0.392625378225, \
    0.392668981806, 0.392712433185, 0.392755732377, 0.3927988794, \
    0.392841874271, 0.392884717005, 0.392927407619, 0.392969946131, \
    0.393012332555, 0.393054566909, 0.393096649209, 0.39313857947, \
    0.39318035771, 0.393221983944, 0.393263458188, 0.393304780457, \
    0.393345950769, 0.393386969139, 0.393427835581, 0.393468550113, \
    0.39350911275, 0.393549523507, 0.3935897824, 0.393629889444, \
    0.393669844655, 0.393709648048, 0.393749299638, 0.393788799441, \
    0.393828147471, 0.393867343743, 0.393906388274, 0.393945281077, \
    0.393984022167, 0.39402261156, 0.39406104927, 0.394099335311, \
    0.394137469699, 0.394175452448, 0.394213283572, 0.394250963087, \
    0.394288491006, 0.394325867343, 0.394363092114, 0.394400165331, \
    0.39443708701, 0.394473857165, 0.394510475809, 0.394546942956, \
    0.394583258621, 0.394619422817, 0.394655435558, 0.394691296858, \
    0.39472700673, 0.394762565188, 0.394797972246, 0.394833227916, \
    0.394868332214, 0.394903285151, 0.394938086741, 0.394972736997, \
    0.395007235934, 0.395041583563, 0.395075779897, 0.395109824951, \
    0.395143718736, 0.395177461266, 0.395211052553, 0.39524449261, \
    0.39527778145, 0.395310919086, 0.39534390553, 0.395376740795, \
    0.395409424892, 0.395441957836, 0.395474339637, 0.395506570308, \
    0.395538649862, 0.39557057831, 0.395602355665, 0.395633981938, \
    0.395665457143, 0.39569678129, 0.395727954391, 0.395758976459, \
    0.395789847504, 0.39582056754, 0.395851136577, 0.395881554626, \
    0.395911821701, 0.395941937811, 0.395971902968, 0.396001717184, \
    0.39603138047, 0.396060892837, 0.396090254297, 0.396119464859, \
    0.396148524537, 0.396177433339, 0.396206191278, 0.396234798364, \
    0.396263254608, 0.396291560021, 0.396319714613, 0.396347718395, \
    0.396375571378, 0.396403273572, 0.396430824988, 0.396458225635, \
    0.396485475525, 0.396512574667, 0.396539523072, 0.39656632075, \
    0.396592967711, 0.396619463965, 0.396645809523, 0.396672004393, \
    0.396698048586, 0.396723942111, 0.396749684979, 0.396775277199, \
    0.396800718781, 0.396826009734, 0.396851150068, 0.396876139792, \
    0.396900978915, 0.396925667448, 0.396950205399, 0.396974592777, \
    0.396998829592, 0.397022915853, 0.397046851568, 0.397070636747, \
    0.397094271399, 0.397117755533, 0.397141089157, 0.39716427228, \
    0.39718730491, 0.397210187058, 0.39723291873, 0.397255499936, \
    0.397277930684, 0.397300210983, 0.39732234084, 0.397344320264, \
    0.397366149264, 0.397387827847, 0.397409356022, 0.397430733797, \
    0.397451961179, 0.397473038177, 0.397493964799, 0.397514741051, \
    0.397535366943, 0.397555842482, 0.397576167675, 0.397596342531, \
    0.397616367056, 0.397636241258, 0.397655965145, 0.397675538724, \
    0.397694962001, 0.397714234986, 0.397733357684, 0.397752330103, \
    0.39777115225, 0.397789824132, 0.397808345755, 0.397826717128, \
    0.397844938256, 0.397863009146, 0.397880929806, 0.397898700242, \
    0.39791632046, 0.397933790467, 0.39795111027, 0.397968279875, \
    0.397985299288, 0.398002168517, 0.398018887566, 0.398035456442, \
    0.398051875152, 0.398068143701, 0.398084262096, 0.398100230343, \
    0.398116048447, 0.398131716414, 0.398147234251, 0.398162601962, \
    0.398177819554, 0.398192887033, 0.398207804404, 0.398222571672, \
    0.398237188843, 0.398251655922, 0.398265972915, 0.398280139828, \
    0.398294156664, 0.39830802343, 0.398321740131, 0.398335306771, \
    0.398348723357, 0.398361989891, 0.398375106381, 0.39838807283, \
    0.398400889243, 0.398413555626, 0.398426071982, 0.398438438316, \
    0.398450654634, 0.398462720938, 0.398474637235, 0.398486403528, \
    0.398498019821, 0.39850948612, 0.398520802428, 0.398531968749, \
    0.398542985087, 0.398553851447, 0.398564567832, 0.398575134247, \
    0.398585550695, 0.398595817181, 0.398605933707, 0.398615900278, \
    0.398625716898, 0.398635383569, 0.398644900296, 0.398654267082, \
    0.39866348393, 0.398672550844, 0.398681467827, 0.398690234883, \
    0.398698852014, 0.398707319224, 0.398715636516, 0.398723803893, \
    0.398731821357, 0.398739688913, 0.398747406562, 0.398754974308, \
    0.398762392153, 0.3987696601, 0.398776778152, 0.398783746311, \
    0.398790564579, 0.39879723296, 0.398803751456, 0.398810120068, \
    0.3988163388, 0.398822407654, 0.398828326631, 0.398834095735, \
    0.398839714966, 0.398845184327, 0.39885050382, 0.398855673448, \
    0.39886069321, 0.398865563111, 0.398870283151, 0.398874853332, \
    0.398879273655, 0.398883544123, 0.398887664737, 0.398891635497, \
    0.398895456407, 0.398899127466, 0.398902648676, 0.398906020039, \
    0.398909241556, 0.398912313228, 0.398915235055, 0.398918007039, \
    0.398920629181, 0.398923101482, 0.398925423943, 0.398927596563, \
    0.398929619345, 0.398931492289, 0.398933215395, 0.398934788664, \
    0.398936212097, 0.398937485693, 0.398938609454, 0.398939583379, \
    0.39894040747, 0.398941081725, 0.398941606146, 0.398941980732, \
    0.398942205484, 0.398942280401, 0.398942280401, 0.398942205484, \
    0.398941980732, 0.398941606146, 0.398941081725, 0.39894040747, \
    0.398939583379, 0.398938609454, 0.398937485693, 0.398936212097, \
    0.398934788664, 0.398933215395, 0.398931492289, 0.398929619345, \
    0.398927596563, 0.398925423943, 0.398923101482, 0.398920629181, \
    0.398918007039, 0.398915235055, 0.398912313228, 0.398909241556, \
    0.398906020039, 0.398902648676, 0.398899127466, 0.398895456407, \
    0.398891635497, 0.398887664737, 0.398883544123, 0.398879273655, \
    0.398874853332, 0.398870283151, 0.398865563111, 0.39886069321, \
    0.398855673448, 0.39885050382, 0.398845184327, 0.398839714966, \
    0.398834095735, 0.398828326631, 0.398822407654, 0.3988163388, \
    0.398810120068, 0.398803751456, 0.39879723296, 0.398790564579, \
    0.398783746311, 0.398776778152, 0.3987696601, 0.398762392153, \
    0.398754974308, 0.398747406562, 0.398739688913, 0.398731821357, \
    0.398723803893, 0.398715636516, 0.398707319224, 0.398698852014, \
    0.398690234883, 0.398681467827, 0.398672550844, 0.39866348393, \
    0.398654267082, 0.398644900296, 0.398635383569, 0.398625716898, \
    0.398615900278, 0.398605933707, 0.398595817181, 0.398585550695, \
    0.398575134247, 0.398564567832, 0.398553851447, 0.398542985087, \
    0.398531968749, 0.398520802428, 0.39850948612, 0.398498019821, \
    0.398486403528, 0.398474637235, 0.398462720938, 0.398450654634, \
    0.398438438316, 0.398426071982, 0.398413555626, 0.398400889243, \
    0.39838807283, 0.398375106381, 0.398361989891, 0.398348723357, \
    0.398335306771, 0.398321740131, 0.39830802343, 0.398294156664, \
    0.398280139828, 0.398265972915, 0.398251655922, 0.398237188843, \
    0.398222571672, 0.398207804404, 0.398192887033, 0.398177819554, \
    0.398162601962, 0.398147234251, 0.398131716414, 0.398116048447, \
    0.398100230343, 0.398084262096, 0.398068143701, 0.398051875152, \
    0.398035456442, 0.398018887566, 0.398002168517, 0.397985299288, \
    0.397968279875, 0.39795111027, 0.397933790467, 0.39791632046, \
    0.397898700242, 0.397880929806, 0.397863009146, 0.397844938256, \
    0.397826717128, 0.397808345755, 0.397789824132, 0.39777115225, \
    0.397752330103, 0.397733357684, 0.397714234986, 0.397694962001, \
    0.397675538724, 0.397655965145, 0.397636241258, 0.397616367056, \
    0.397596342531, 0.397576167675, 0.397555842482, 0.397535366943, \
    0.397514741051, 0.397493964799, 0.397473038177, 0.397451961179, \
    0.397430733797, 0.397409356022, 0.397387827847, 0.397366149264, \
    0.397344320264, 0.39732234084, 0.397300210983, 0.397277930684, \
    0.397255499936, 0.39723291873, 0.397210187058, 0.39718730491, \
    0.39716427228, 0.397141089157, 0.397117755533, 0.397094271399, \
    0.397070636747, 0.397046851568, 0.397022915853, 0.396998829592, \
    0.396974592777, 0.396950205399, 0.396925667448, 0.396900978915, \
    0.396876139792, 0.396851150068, 0.396826009734, 0.396800718781, \
    0.396775277199, 0.396749684979, 0.396723942111, 0.396698048586, \
    0.396672004393, 0.396645809523, 0.396619463965, 0.396592967711, \
    0.39656632075, 0.396539523072, 0.396512574667, 0.396485475525, \
    0.396458225635, 0.396430824988, 0.396403273572, 0.396375571378, \
    0.396347718395, 0.396319714613, 0.396291560021, 0.396263254608, \
    0.396234798364, 0.396206191278, 0.396177433339, 0.396148524537, \
    0.396119464859, 0.396090254297, 0.396060892837, 0.39603138047, \
    0.396001717184, 0.395971902968, 0.395941937811, 0.395911821701, \
    0.395881554626, 0.395851136577, 0.39582056754, 0.395789847504, \
    0.395758976459, 0.395727954391, 0.39569678129, 0.395665457143, \
    0.395633981938, 0.395602355665, 0.39557057831, 0.395538649862, \
    0.395506570308, 0.395474339637, 0.395441957836, 0.395409424892, \
    0.395376740795, 0.39534390553, 0.395310919086, 0.39527778145, \
    0.39524449261, 0.395211052553, 0.395177461266, 0.395143718736, \
    0.395109824951, 0.395075779897, 0.395041583563, 0.395007235934, \
    0.394972736997, 0.394938086741, 0.394903285151, 0.394868332214, \
    0.394833227916, 0.394797972246, 0.394762565188, 0.39472700673, \
    0.394691296858, 0.394655435558, 0.394619422817, 0.394583258621, \
    0.394546942956, 0.394510475809, 0.394473857165, 0.39443708701, \
    0.394400165331, 0.394363092114, 0.394325867343, 0.394288491006, \
    0.394250963087, 0.394213283572, 0.394175452448, 0.394137469699, \
    0.394099335311, 0.39406104927, 0.39402261156, 0.393984022167, \
    0.393945281077, 0.393906388274, 0.393867343743, 0.393828147471, \
    0.393788799441, 0.393749299638, 0.393709648048, 0.393669844655, \
    0.393629889444, 0.3935897824, 0.393549523507, 0.39350911275, \
    0.393468550113, 0.393427835581, 0.393386969139, 0.393345950769, \
    0.393304780457, 0.393263458188, 0.393221983944, 0.39318035771, \
    0.39313857947, 0.393096649209, 0.393054566909, 0.393012332555, \
    0.392969946131, 0.392927407619, 0.392884717005, 0.392841874271, \
    0.3927988794, 0.392755732377, 0.392712433185, 0.392668981806, \
    0.392625378225, 0.392581622425, 0.392537714388, 0.392493654097, \
    0.392449441536, 0.392405076688, 0.392360559535, 0.392315890061, \
    0.392271068247, 0.392226094077, 0.392180967534, 0.392135688599, \
    0.392090257256, 0.392044673487, 0.391998937274, 0.391953048599, \
    0.391907007445, 0.391860813794, 0.391814467628, 0.39176796893, \
    0.39172131768, 0.391674513861, 0.391627557456, 0.391580448445, \
    0.39153318681, 0.391485772534, 0.391438205597, 0.391390485981, \
    0.391342613669, 0.39129458864, 0.391246410877, 0.391198080361, \
    0.391149597072, 0.391100960993, 0.391052172104, 0.391003230387, \
    0.390954135822, 0.39090488839, 0.390855488072, 0.390805934848, \
    0.390756228701, 0.390706369609, 0.390656357554, 0.390606192517, \
    0.390555874477, 0.390505403415, 0.390454779312, 0.390404002147, \
    0.390353071901, 0.390301988554, 0.390250752086, 0.390199362477, \
    0.390147819707, 0.390096123756, 0.390044274604, 0.38999227223, \
    0.389940116614, 0.389887807735, 0.389835345574, 0.389782730109, \
    0.38972996132, 0.389677039187, 0.389623963688, 0.389570734804, \
    0.389517352512, 0.389463816792, 0.389410127623, 0.389356284985, \
    0.389302288855, 0.389248139213, 0.389193836037, 0.389139379307, \
    0.389084769, 0.389030005096, 0.388975087572, 0.388920016407, \
    0.38886479158, 0.388809413069, 0.388753880852, 0.388698194907, \
    0.388642355212, 0.388586361746, 0.388530214485, 0.388473913409, \
    0.388417458495, 0.38836084972, 0.388304087062, 0.3882471705, \
    0.38819010001, 0.388132875569, 0.388075497156, 0.388017964748, \
    0.387960278321, 0.387902437854, 0.387844443323, 0.387786294705, \
    0.387727991978, 0.387669535118, 0.387610924101, 0.387552158906, \
    0.387493239508, 0.387434165885, 0.387374938013, 0.387315555867, \
    0.387256019426, 0.387196328665, 0.387136483561, 0.387076484089, \
    0.387016330226, 0.386956021948, 0.386895559231, 0.386834942052, \
    0.386774170385, 0.386713244207, 0.386652163494, 0.386590928221, \
    0.386529538363, 0.386467993897, 0.386406294798, 0.386344441042, \
    0.386282432603, 0.386220269457, 0.386157951579, 0.386095478944, \
    0.386032851528, 0.385970069305, 0.38590713225, 0.385844040338, \
    0.385780793545, 0.385717391843, 0.385653835209, 0.385590123617, \
    0.385526257042, 0.385462235457, 0.385398058837, 0.385333727156, \
    0.385269240389, 0.38520459851, 0.385139801493, 0.385074849312, \
    0.38500974194, 0.384944479352, 0.384879061522, 0.384813488423, \
    0.384747760028, 0.384681876312, 0.384615837248, 0.384549642809, \
    0.384483292969, 0.384416787701, 0.384350126978, 0.384283310773, \
    0.38421633906, 0.384149211811, 0.384081929, 0.384014490599, \
    0.383946896581, 0.383879146918, 0.383811241584, 0.383743180551, \
    0.383674963791, 0.383606591278, 0.383538062982, 0.383469378877, \
    0.383400538934, 0.383331543127, 0.383262391426, 0.383193083804, \
    0.383123620232, 0.383054000684, 0.382984225129, 0.382914293541, \
    0.382844205891, 0.382773962149, 0.382703562288, 0.38263300628, \
    0.382562294094, 0.382491425704, 0.382420401079, 0.382349220191, \
    0.38227788301, 0.382206389509, 0.382134739657, 0.382062933426, \
    0.381990970787, 0.381918851709, 0.381846576163, 0.381774144121, \
    0.381701555551, 0.381628810426, 0.381555908715, 0.381482850387, \
    0.381409635414, 0.381336263766, 0.381262735412, 0.381189050322, \
    0.381115208466, 0.381041209813, 0.380967054335, 0.380892741999, \
    0.380818272776, 0.380743646634, 0.380668863545, 0.380593923475, \
    0.380518826396, 0.380443572275, 0.380368161083, 0.380292592787, \
    0.380216867358, 0.380140984763, 0.380064944972, 0.379988747952, \
    0.379912393674, 0.379835882104, 0.379759213212, 0.379682386967, \
    0.379605403335, 0.379528262286, 0.379450963788, 0.379373507808, \
    0.379295894315, 0.379218123276, 0.37914019466, 0.379062108433, \
    0.378983864565, 0.378905463021, 0.378826903771, 0.37874818678, \
    0.378669312017, 0.378590279449, 0.378511089043, 0.378431740766, \
    0.378352234585, 0.378272570466, 0.378192748378, 0.378112768286, \
    0.378032630158, 0.37795233396, 0.377871879658, 0.377791267219, \
    0.377710496609, 0.377629567795, 0.377548480743, 0.377467235419, \
    0.377385831788, 0.377304269818, 0.377222549474, 0.377140670721, \
    0.377058633526, 0.376976437854, 0.376894083671, 0.376811570942, \
    0.376728899632, 0.376646069707, 0.376563081133, 0.376479933873, \
    0.376396627894, 0.37631316316, 0.376229539637, 0.376145757289, \
    0.37606181608, 0.375977715976, 0.375893456941, 0.37580903894, \
    0.375724461937, 0.375639725896, 0.375554830782, 0.375469776558, \
    0.375384563189, 0.37529919064, 0.375213658872, 0.375127967852, \
    0.375042117542, 0.374956107906, 0.374869938907, 0.374783610509, \
    0.374697122676, 0.374610475371, 0.374523668557, 0.374436702197, \
    0.374349576255, 0.374262290692, 0.374174845473, 0.37408724056, \
    0.373999475916, 0.373911551503, 0.373823467284, 0.373735223221, \
    0.373646819277, 0.373558255414, 0.373469531595, 0.373380647781, \
    0.373291603934, 0.373202400017, 0.373113035991, 0.373023511819, \
    0.372933827461, 0.372843982879, 0.372753978036, 0.372663812892, \
    0.372573487408, 0.372483001547, 0.372392355268, 0.372301548534, \
    0.372210581305, 0.372119453543, 0.372028165207, 0.371936716259, \
    0.371845106659, 0.371753336368, 0.371661405347, 0.371569313555, \
    0.371477060953, 0.371384647502, 0.371292073161, 0.37119933789, \
    0.371106441649, 0.371013384399, 0.370920166098, 0.370826786707, \
    0.370733246185, 0.370639544492, 0.370545681587, 0.370451657429, \
    0.370357471977, 0.370263125191, 0.37016861703, 0.370073947452, \
    0.369979116417, 0.369884123883, 0.369788969809, 0.369693654153, \
    0.369598176874, 0.36950253793, 0.36940673728, 0.369310774882, \
    0.369214650693, 0.369118364673, 0.369021916778, 0.368925306967, \
    0.368828535197, 0.368731601427, 0.368634505613, 0.368537247713, \
    0.368439827684, 0.368342245484, 0.36824450107, 0.368146594399, \
    0.368048525428, 0.367950294114, 0.367851900414, 0.367753344284, \
    0.36765462568, 0.367555744561, 0.367456700881, 0.367357494598, \
    0.367258125667, 0.367158594044, 0.367058899687, 0.36695904255, \
    0.366859022589, 0.366758839761, 0.36665849402, 0.366557985323, \
    0.366457313625, 0.366356478881, 0.366255481046, 0.366154320077, \
    0.366052995927, 0.365951508551, 0.365849857906, 0.365748043945, \
    0.365646066623, 0.365543925894, 0.365441621714, 0.365339154037, \
    0.365236522816, 0.365133728007, 0.365030769562, 0.364927647437, \
    0.364824361585, 0.364720911959, 0.364617298515, 0.364513521204, \
    0.364409579981, 0.364305474799, 0.364201205612, 0.364096772372, \
    0.363992175032, 0.363887413546, 0.363782487867, 0.363677397947, \
    0.36357214374, 0.363466725196, 0.36336114227, 0.363255394914, \
    0.363149483079, 0.363043406718, 0.362937165783, 0.362830760226, \
    0.36272419, 0.362617455054, 0.362510555343, 0.362403490816, \
    0.362296261425, 0.362188867123, 0.362081307859, 0.361973583586, \
    0.361865694253, 0.361757639813, 0.361649420216, 0.361541035413, \
    0.361432485354, 0.36132376999, 0.361214889271, 0.361105843148, \
    0.360996631571, 0.360887254489, 0.360777711854, 0.360668003615, \
    0.360558129721, 0.360448090122, 0.360337884769, 0.36022751361, \
    0.360116976594, 0.360006273672, 0.359895404792, 0.359784369903, \
    0.359673168954, 0.359561801893, 0.359450268671, 0.359338569235, \
    0.359226703533, 0.359114671515, 0.359002473128, 0.358890108321, \
    0.358777577041, 0.358664879237, 0.358552014857, 0.358438983847, \
    0.358325786157, 0.358212421732, 0.358098890522, 0.357985192472, \
    0.357871327531, 0.357757295645, 0.357643096761, 0.357528730826, \
    0.357414197787, 0.35729949759, 0.357184630183, 0.35706959551, \
    0.356954393519, 0.356839024156, 0.356723487367, 0.356607783098, \
    0.356491911294, 0.356375871902, 0.356259664866, 0.356143290133, \
    0.356026747648, 0.355910037356, 0.355793159202, 0.355676113131, \
    0.355558899089, 0.355441517019, 0.355323966867, 0.355206248577, \
    0.355088362094, 0.354970307363, 0.354852084326, 0.354733692928, \
    0.354615133114, 0.354496404828, 0.354377508012, 0.35425844261, \
    0.354139208567, 0.354019805826, 0.353900234329, 0.35378049402, \
    0.353660584842, 0.353540506738, 0.353420259651, 0.353299843523, \
    0.353179258297, 0.353058503916, 0.352937580322, 0.352816487456, \
    0.352695225262, 0.35257379368, 0.352452192653, 0.352330422124, \
    0.352208482032, 0.35208637232, 0.351964092929, 0.3518416438, \
    0.351719024875, 0.351596236094, 0.351473277398, 0.351350148728, \
    0.351226850025, 0.351103381229, 0.350979742281, 0.35085593312, \
    0.350731953687, 0.350607803923, 0.350483483765, 0.350358993156, \
    0.350234332033, 0.350109500337, 0.349984498007, 0.349859324983, \
    0.349733981203, 0.349608466606, 0.349482781131, 0.349356924717, \
    0.349230897303, 0.349104698827, 0.348978329228, 0.348851788443, \
    0.348725076411, 0.348598193069, 0.348471138357, 0.34834391221, \
    0.348216514568, 0.348088945366, 0.347961204544, 0.347833292037, \
    0.347705207784, 0.34757695172, 0.347448523782, 0.347319923909, \
    0.347191152035, 0.347062208097, 0.346933092032, 0.346803803775, \
    0.346674343264, 0.346544710432, 0.346414905218, 0.346284927555, \
    0.346154777379, 0.346024454627, 0.345893959232, 0.34576329113, \
    0.345632450257, 0.345501436546, 0.345370249932, 0.345238890351, \
    0.345107357736, 0.344975652022, 0.344843773142, 0.344711721031, \
    0.344579495623, 0.344447096851, 0.344314524649, 0.344181778951, \
    0.344048859689, 0.343915766796, 0.343782500207, 0.343649059853, \
    0.343515445668, 0.343381657583, 0.343247695533, 0.343113559448, \
    0.342979249261, 0.342844764904, 0.342710106308, 0.342575273407, \
    0.342440266131, 0.342305084412, 0.34216972818, 0.342034197368, \
    0.341898491907, 0.341762611726, 0.341626556758, 0.341490326932, \
    0.341353922179, 0.34121734243, 0.341080587614, 0.340943657662, \
    0.340806552503, 0.340669272067, 0.340531816284, 0.340394185084, \
    0.340256378395, 0.340118396147, 0.339980238268, 0.339841904688, \
    0.339703395335, 0.339564710138, 0.339425849025, 0.339286811925, \
    0.339147598766, 0.339008209475, 0.33886864398, 0.33872890221, \
    0.338588984091, 0.33844888955, 0.338308618517, 0.338168170916, \
    0.338027546675, 0.337886745721, 0.337745767981, 0.33760461338, \
    0.337463281846, 0.337321773304, 0.33718008768, 0.3370382249, \
    0.336896184891, 0.336753967576, 0.336611572882, 0.336469000734, \
    0.336326251057, 0.336183323776, 0.336040218815, 0.335896936099, \
    0.335753475553, 0.335609837101, 0.335466020667, 0.335322026174, \
    0.335177853547, 0.33503350271, 0.334888973585, 0.334744266096, \
    0.334599380166, 0.334454315719, 0.334309072676, 0.334163650961, \
    0.334018050496, 0.333872271204, 0.333726313006, 0.333580175825, \
    0.333433859582, 0.3332873642, 0.333140689599, 0.332993835701, \
    0.332846802427, 0.332699589699, 0.332552197437, 0.332404625561, \
    0.332256873993, 0.332108942652, 0.331960831459, 0.331812540334, \
    0.331664069197, 0.331515417967, 0.331366586564, 0.331217574907, \
    0.331068382916, 0.330919010508, 0.330769457604, 0.330619724122, \
    0.33046980998, 0.330319715097, 0.330169439391, 0.330018982779, \
    0.32986834518, 0.329717526511, 0.32956652669, 0.329415345633, \
    0.329263983259, 0.329112439483, 0.328960714223, 0.328808807396, \
    0.328656718917, 0.328504448702, 0.328351996669, 0.328199362732, \
    0.328046546808, 0.327893548812, 0.327740368658, 0.327587006263, \
    0.327433461542, 0.327279734408, 0.327125824778, 0.326971732564, \
    0.326817457682, 0.326663000045, 0.326508359567, 0.326353536163, \
    0.326198529745, 0.326043340226, 0.325887967521, 0.325732411541, \
    0.3255766722, 0.325420749411, 0.325264643085, 0.325108353134, \
    0.324951879472, 0.324795222009, 0.324638380658, 0.324481355329, \
    0.324324145934, 0.324166752385, 0.324009174591, 0.323851412464, \
    0.323693465915, 0.323535334852, 0.323377019188, 0.323218518831, \
    0.323059833691, 0.322900963677, 0.322741908701, 0.322582668669, \
    0.322423243491, 0.322263633077, 0.322103837334, 0.321943856171, \
    0.321783689496, 0.321623337217, 0.321462799242, 0.321302075479, \
    0.321141165834, 0.320980070215, 0.320818788529, 0.320657320683, \
    0.320495666583, 0.320333826135, 0.320171799247, 0.320009585823, \
    0.31984718577, 0.319684598993, 0.319521825397, 0.319358864888, \
    0.31919571737, 0.319032382749, 0.318868860929, 0.318705151813, \
    0.318541255307, 0.318377171315, 0.318212899739, 0.318048440483, \
    0.317883793451, 0.317718958546, 0.31755393567, 0.317388724726, \
    0.317223325617, 0.317057738245, 0.316891962512, 0.31672599832, \
    0.31655984557, 0.316393504163, 0.316226974001, 0.316060254985, \
    0.315893347016, 0.315726249993, 0.315558963818, 0.31539148839, \
    0.315223823609, 0.315055969374, 0.314887925586, 0.314719692144, \
    0.314551268945, 0.31438265589, 0.314213852877, 0.314044859803, \
    0.313875676567, 0.313706303067, 0.313536739201, 0.313366984865, \
    0.313197039958, 0.313026904375, 0.312856578014, 0.312686060772, \
    0.312515352544, 0.312344453226, 0.312173362715, 0.312002080905, \
    0.311830607693, 0.311658942973, 0.31148708664, 0.31131503859, \
    0.311142798715, 0.310970366911, 0.310797743071, 0.31062492709, \
    0.31045191886, 0.310278718275, 0.310105325228, 0.309931739611, \
    0.309757961317, 0.309583990239, 0.309409826268, 0.309235469297, \
    0.309060919216, 0.308886175918, 0.308711239292, 0.308536109231, \
    0.308360785624, 0.308185268362, 0.308009557336, 0.307833652434, \
    0.307657553547, 0.307481260563, 0.307304773373, 0.307128091864, \
    0.306951215926, 0.306774145446, 0.306596880314, 0.306419420416, \
    0.306241765641, 0.306063915875, 0.305885871006, 0.305707630921, \
    0.305529195506, 0.305350564647, 0.305171738232, 0.304992716144, \
    0.304813498271, 0.304634084497, 0.304454474707, 0.304274668786, \
    0.304094666619, 0.30391446809, 0.303734073083, 0.303553481481, \
    0.303372693168, 0.303191708028, 0.303010525942, 0.302829146795, \
    0.302647570468, 0.302465796843, 0.302283825802, 0.302101657227, \
    0.301919290999, 0.301736726999, 0.301553965108, 0.301371005207, \
    0.301187847175, 0.301004490893, 0.30082093624, 0.300637183096, \
    0.300453231339, 0.30026908085, 0.300084731505, 0.299900183184, \
    0.299715435764, 0.299530489123, 0.299345343139, 0.299159997689, \
    0.298974452649, 0.298788707897, 0.298602763308, 0.298416618759, \
    0.298230274125, 0.298043729282, 0.297856984104, 0.297670038468, \
    0.297482892246, 0.297295545315, 0.297107997546, 0.296920248815, \
    0.296732298995, 0.296544147958, 0.296355795578, 0.296167241727, \
    0.295978486277, 0.295789529101, 0.295600370069, 0.295411009053, \
    0.295221445924, 0.295031680553, 0.294841712811, 0.294651542566, \
    0.29446116969, 0.294270594051, 0.294079815519, 0.293888833963, \
    0.293697649251, 0.293506261251, 0.293314669832, 0.29312287486, \
    0.292930876204, 0.292738673731, 0.292546267306, 0.292353656796, \
    0.292160842068, 0.291967822987, 0.291774599419, 0.291581171228, \
    0.29138753828, 0.291193700439, 0.290999657568, 0.290805409533, \
    0.290610956195, 0.290416297419, 0.290221433068, 0.290026363003, \
    0.289831087087, 0.289635605182, 0.289439917148, 0.289244022849, \
    0.289047922144, 0.288851614893, 0.288655100957, 0.288458380196, \
    0.28826145247, 0.288064317636, 0.287866975555, 0.287669426085, \
    0.287471669084, 0.287273704409, 0.287075531918, 0.286877151468, \
    0.286678562916, 0.286479766119, 0.286280760932, 0.286081547211, \
    0.285882124811, 0.285682493588, 0.285482653395, 0.285282604088, \
    0.285082345521, 0.284881877546, 0.284681200017, 0.284480312788, \
    0.284279215709, 0.284077908635, 0.283876391415, 0.283674663903, \
    0.283472725948, 0.283270577402, 0.283068218114, 0.282865647935, \
    0.282662866715, 0.282459874302, 0.282256670545, 0.282053255293, \
    0.281849628394, 0.281645789695, 0.281441739045, 0.281237476289, \
    0.281033001275, 0.280828313848, 0.280623413854, 0.280418301139, \
    0.280212975549, 0.280007436926, 0.279801685116, 0.279595719963, \
    0.27938954131, 0.279183149, 0.278976542875, 0.278769722779, \
    0.278562688553, 0.278355440038, 0.278147977076, 0.277940299507, \
    0.277732407172, 0.27752429991, 0.277315977561, 0.277107439965, \
    0.276898686958, 0.276689718381, 0.276480534071, 0.276271133865, \
    0.2760615176, 0.275851685114, 0.275641636241, 0.275431370818, \
    0.275220888681, 0.275010189664, 0.274799273601, 0.274588140328, \
    0.274376789677, 0.274165221481, 0.273953435575, 0.273741431789, \
    0.273529209956, 0.273316769908, 0.273104111476, 0.272891234489, \
    0.272678138779, 0.272464824175, 0.272251290507, 0.272037537604, \
    0.271823565293, 0.271609373403, 0.271394961762, 0.271180330196, \
    0.270965478533, 0.270750406598, 0.270535114218, 0.270319601217, \
    0.270103867421, 0.269887912653, 0.269671736739, 0.2694553395, \
    0.269238720761, 0.269021880344, 0.268804818071, 0.268587533763, \
    0.268370027242, 0.268152298328, 0.267934346842, 0.267716172603, \
    0.26749777543, 0.267279155143, 0.26706031156, 0.266841244498, \
    0.266621953774, 0.266402439207, 0.266182700611, 0.265962737803, \
    0.265742550598, 0.265522138811, 0.265301502256, 0.265080640748, \
    0.2648595541, 0.264638242124, 0.264416704633, 0.264194941439, \
    0.263972952353, 0.263750737186, 0.263528295749, 0.263305627851, \
    0.263082733302, 0.26285961191, 0.262636263484, 0.262412687831, \
    0.26218888476, 0.261964854076, 0.261740595585, 0.261516109095, \
    0.261291394408, 0.261066451331, 0.260841279668, 0.260615879221, \
    0.260390249794, 0.260164391189, 0.259938303209, 0.259711985655, \
    0.259485438327, 0.259258661026, 0.259031653551, 0.258804415703, \
    0.258576947278, 0.258349248077, 0.258121317895, 0.25789315653, \
    0.257664763779, 0.257436139437, 0.2572072833, 0.256978195162, \
    0.256748874817, 0.256519322059, 0.256289536681, 0.256059518475, \
    0.255829267233, 0.255598782747, 0.255368064807, 0.255137113202, \
    0.254905927723, 0.254674508159, 0.254442854297, 0.254210965925, \
    0.253978842831, 0.253746484801, 0.253513891621, 0.253281063075, \
    0.253047998949, 0.252814699027, 0.252581163092, 0.252347390927, \
    0.252113382314, 0.251879137035, 0.251644654871, 0.251409935601, \
    0.251174979007, 0.250939784865, 0.250704352956, 0.250468683057, \
    0.250232774945, 0.249996628397, 0.249760243188, 0.249523619094, \
    0.249286755888, 0.249049653346, 0.24881231124, 0.248574729343, \
    0.248336907427, 0.248098845263, 0.247860542621, 0.247621999273, \
    0.247383214985, 0.247144189529, 0.24690492267, 0.246665414177, \
    0.246425663816, 0.246185671353, 0.245945436553, 0.24570495918, \
    0.245464238999, 0.245223275772, 0.244982069261, 0.244740619229, \
    0.244498925435, 0.244256987642, 0.244014805607, 0.24377237909, \
    0.243529707849, 0.243286791641, 0.243043630222, 0.24280022335, \
    0.242556570778, 0.242312672262, 0.242068527555, 0.241824136409, \
    0.241579498578, 0.241334613813, 0.241089481863, 0.240844102481, \
    0.240598475413, 0.240352600409, 0.240106477217, 0.239860105583, \
    0.239613485254, 0.239366615975, 0.23911949749, 0.238872129544, \
    0.238624511878, 0.238376644236, 0.238128526359, 0.237880157987, \
    0.237631538861, 0.237382668719, 0.2371335473, 0.23688417434, \
    0.236634549577, 0.236384672746, 0.236134543582, 0.23588416182, \
    0.235633527192, 0.235382639431, 0.235131498268, 0.234880103436, \
    0.234628454662, 0.234376551677, 0.234124394209, 0.233871981984, \
    0.233619314731, 0.233366392173, 0.233113214036, 0.232859780045, \
    0.232606089921, 0.232352143387, 0.232097940164, 0.231843479974, \
    0.231588762534, 0.231333787564, 0.231078554782, 0.230823063904, \
    0.230567314646, 0.230311306723, 0.23005503985, 0.229798513738, \
    0.229541728101, 0.22928468265, 0.229027377095, 0.228769811145, \
    0.22851198451, 0.228253896895, 0.227995548009, 0.227736937556, \
    0.227478065241, 0.227218930768, 0.22695953384, 0.226699874157, \
    0.226439951422, 0.226179765333, 0.22591931559, 0.22565860189, \
    0.22539762393, 0.225136381406, 0.224874874012, 0.224613101442, \
    0.224351063389, 0.224088759545, 0.2238261896, 0.223563353244, \
    0.223300250165, 0.223036880051, 0.222773242589, 0.222509337463, \
    0.222245164359, 0.22198072296, 0.221716012947, 0.221451034002, \
    0.221185785805, 0.220920268035, 0.220654480371, 0.220388422488, \
    0.220122094062, 0.219855494768, 0.21958862428, 0.21932148227, \
    0.219054068409, 0.218786382367, 0.218518423813, 0.218250192415, \
    0.21798168784, 0.217712909752, 0.217443857818, 0.217174531699, \
    0.216904931057, 0.216635055555, 0.21636490485, 0.216094478602, \
    0.215823776468, 0.215552798104, 0.215281543164, 0.215010011303, \
    0.214738202173, 0.214466115425, 0.214193750709, 0.213921107674, \
    0.213648185967, 0.213374985234, 0.213101505121, 0.21282774527, \
    0.212553705325, 0.212279384926, 0.212004783714, 0.211729901327, \
    0.211454737402, 0.211179291575, 0.21090356348, 0.210627552752, \
    0.210351259021, 0.210074681919, 0.209797821075, 0.209520676117, \
    0.209243246671, 0.208965532363, 0.208687532816, 0.208409247653, \
    0.208130676495, 0.207851818961, 0.20757267467, 0.207293243239, \
    0.207013524284, 0.206733517417, 0.206453222252, 0.2061726384, \
    0.205891765471, 0.205610603072, 0.205329150811, 0.205047408293, \
    0.204765375121, 0.204483050898, 0.204200435225, 0.203917527701, \
    0.203634327924, 0.20335083549, 0.203067049994, 0.202782971029, \
    0.202498598186, 0.202213931056, 0.201928969228, 0.201643712287, \
    0.20135815982, 0.20107231141, 0.20078616664, 0.200499725089, \
    0.200212986337, 0.199925949961, 0.199638615537, 0.199350982639, \
    0.199063050838, 0.198774819706, 0.198486288812, 0.198197457722, \
    0.197908326003, 0.197618893218, 0.197329158929, 0.197039122697, \
    0.196748784081, 0.196458142637, 0.196167197921, 0.195875949485, \
    0.195584396882, 0.195292539661, 0.19500037737, 0.194707909556, \
    0.194415135763, 0.194122055533, 0.193828668408, 0.193534973925, \
    0.193240971621, 0.192946661033, 0.192652041693, 0.192357113132, \
    0.192061874879, 0.191766326463, 0.191470467408, 0.191174297238, \
    0.190877815475, 0.190581021638, 0.190283915244, 0.189986495811, \
    0.18968876285, 0.189390715873, 0.189092354391, 0.188793677911, \
    0.188494685937, 0.188195377973, 0.187895753521, 0.18759581208, \
    0.187295553146, 0.186994976215, 0.186694080779, 0.186392866329, \
    0.186091332353, 0.185789478338, 0.185487303768, 0.185184808123, \
    0.184881990885, 0.18457885153, 0.184275389534, 0.183971604368, \
    0.183667495505, 0.183363062412, 0.183058304554, 0.182753221396, \
    0.182447812399, 0.182142077022, 0.18183601472, 0.181529624949, \
    0.18122290716, 0.180915860803, 0.180608485323, 0.180300780166, \
    0.179992744774, 0.179684378585, 0.179375681037, 0.179066651564, \
    0.178757289598, 0.178447594568, 0.178137565902, 0.177827203022, \
    0.177516505351, 0.177205472308, 0.176894103309, 0.176582397766, \
    0.176270355092, 0.175957974695, 0.175645255979, 0.175332198348, \
    0.175018801202, 0.174705063937, 0.174390985949, 0.174076566628, \
    0.173761805364, 0.173446701542, 0.173131254545, 0.172815463755, \
    0.172499328546, 0.172182848295, 0.171866022373, 0.171548850146, \
    0.171231330982, 0.170913464242, 0.170595249286, 0.170276685469, \
    0.169957772145, 0.169638508664, 0.169318894373, 0.168998928615, \
    0.168678610731, 0.168357940058, 0.16803691593, 0.167715537679, \
    0.167393804631, 0.167071716111, 0.16674927144, 0.166426469936, \
    0.166103310913, 0.165779793681, 0.165455917548, 0.165131681818, \
    0.164807085792, 0.164482128766, 0.164156810034, 0.163831128886, \
    0.163505084608, 0.163178676483, 0.162851903789, 0.162524765803, \
    0.162197261796, 0.161869391036, 0.161541152788, 0.161212546311, \
    0.160883570863, 0.160554225695, 0.160224510058, 0.159894423197, \
    0.159563964351, 0.159233132759, 0.158901927654, 0.158570348265, \
    0.158238393817, 0.15790606353, 0.157573356623, 0.157240272307, \
    0.156906809791, 0.156572968279, 0.156238746972, 0.155904145066, \
    0.155569161751, 0.155233796214, 0.15489804764, 0.154561915205, \
    0.154225398084, 0.153888495445, 0.153551206454, 0.153213530271, \
    0.152875466051, 0.152537012946, 0.152198170101, 0.151858936658, \
    0.151519311753, 0.151179294519, 0.150838884082, 0.150498079565, \
    0.150156880085, 0.149815284753, 0.149473292678, 0.149130902961, \
    0.148788114699, 0.148444926984, 0.148101338903, 0.147757349537, \
    0.147412957962, 0.147068163249, 0.146722964463, 0.146377360665, \
    0.146031350908, 0.145684934242, 0.14533810971, 0.144990876349, \
    0.144643233193, 0.144295179266, 0.14394671359, 0.143597835179, \
    0.143248543043, 0.142898836183, 0.142548713597, 0.142198174276, \
    0.141847217205, 0.141495841361, 0.141144045718, 0.140791829241, \
    0.14043919089, 0.140086129618, 0.139732644373, 0.139378734095, \
    0.139024397717, 0.138669634167, 0.138314442365, 0.137958821225, \
    0.137602769653, 0.137246286551, 0.13688937081, 0.136532021316, \
    0.13617423695, 0.135816016581, 0.135457359075, 0.13509826329, \
    0.134738728074, 0.13437875227, 0.134018334713, 0.13365747423, \
    0.133296169642, 0.132934419758, 0.132572223385, 0.132209579317, \
    0.131846486342, 0.131482943242, 0.131118948787, 0.130754501741, \
    0.13038960086, 0.130024244891, 0.129658432571, 0.129292162631, \
    0.128925433793, 0.128558244767, 0.128190594259, 0.127822480963, \
    0.127453903564, 0.127084860738, 0.126715351154, 0.126345373469, \
    0.125974926331, 0.12560400838, 0.125232618245, 0.124860754545, \
    0.12448841589, 0.124115600881, 0.123742308106, 0.123368536146, \
    0.12299428357, 0.122619548937, 0.122244330795, 0.121868627682, \
    0.121492438126, 0.121115760642, 0.120738593735, 0.120360935901, \
    0.119982785621, 0.119604141367, 0.1192250016, 0.118845364768, \
    0.118465229306, 0.118084593641, 0.117703456185, 0.117321815339, \
    0.11693966949, 0.116557017014, 0.116173856276, 0.115790185624, \
    0.115406003396, 0.115021307918, 0.1146360975, 0.11425037044, \
    0.113864125022, 0.113477359516, 0.113090072181, 0.112702261257, \
    0.112313924974, 0.111925061545, 0.111535669171, 0.111145746034, \
    0.110755290307, 0.110364300142, 0.109972773679, 0.109580709043, \
    0.10918810434, 0.108794957663, 0.108401267088, 0.108007030675, \
    0.107612246467, 0.10721691249, 0.106821026753, 0.106424587249, \
    0.106027591953, 0.10563003882, 0.105231925791, 0.104833250787, \
    0.10443401171, 0.104034206444, 0.103633832853, 0.103232888785, \
    0.102831372066, 0.102429280502, 0.102026611881, 0.101623363968, \
    0.10121953451, 0.100815121233, 0.100410121841, 0.100004534016, \
    0.0995983554201, 0.0991915836918, 0.098784216448, 0.098376251283, \
    0.0979676857678, 0.0975585174503, 0.0971487438546, 0.0967383624809, \
    0.0963273708049, 0.0959157662776, 0.095503546325, 0.0950907083474, \
    0.0946772497194, 0.0942631677893, 0.0938484598786, 0.0934331232819, \
    0.0930171552661, 0.0926005530704, 0.0921833139053, 0.0917654349529, \
    0.0913469133655, 0.0909277462662, 0.0905079307475, 0.0900874638713, \
    0.0896663426683, 0.0892445641375, 0.0888221252457, 0.0883990229268, \
    0.0879752540816, 0.0875508155769, 0.0871257042449, 0.0866999168832, \
    0.0862734502535, 0.0858463010813, 0.0854184660553, 0.0849899418268, \
    0.084560725009, 0.0841308121761, 0.0837001998631, 0.0832688845646, \
    0.0828368627345, 0.082404130785, 0.0819706850859, 0.081536521964, \
    0.081101637702, 0.080666028538, 0.0802296906646, 0.0797926202279, \
    0.0793548133268, 0.078916266012, 0.0784769742851, 0.0780369340979, \
    0.077596141351, 0.0771545918932, 0.0767122815202, 0.076269205974, \
    0.0758253609412, 0.0753807420524, 0.0749353448811, 0.074489164942, \
    0.0740421976905, 0.0735944385211, 0.0731458827663, 0.0726965256949, \
    0.0722463625114, 0.0717953883543, 0.0713435982942, 0.0708909873334, \
    0.0704375504035, 0.0699832823643, 0.0695281780022, 0.0690722320286, \
    0.0686154390782, 0.0681577937072, 0.0676992903918, 0.0672399235259, \
    0.0667796874201, 0.0663185762986, 0.0658565842984, 0.0653937054663, \
    0.0649299337573, 0.0644652630325, 0.0639996870564, 0.0635331994951, \
    0.0630657939132, 0.0625974637723, 0.0621282024276, 0.0616580031256, \
    0.0611868590013, 0.0607147630756, 0.060241708252, 0.0597676873138, \
    0.059292692921, 0.058816717607, 0.0583397537752, 0.0578617936955, \
    0.0573828295011, 0.0569028531841, 0.0564218565922, 0.0559398314244, \
    0.0554567692269, 0.054972661389, 0.0544874991381, 0.0540012735356, \
    0.053513975472, 0.0530255956613, 0.0525361246366, 0.052045552744, \
    0.0515538701374, 0.0510610667724, 0.0505671324, 0.0500720565609, \
    0.0495758285778, 0.0490784375496, 0.0485798723434, 0.048080121587, \
    0.0475791736615, 0.0470770166928, 0.0465736385427, 0.0460690268006, \
    0.0455631687734, 0.0450560514761, 0.0445476616215, 0.0440379856092, \
    0.0435270095144, 0.0430147190762, 0.0425010996849, 0.0419861363691, \
    0.0414698137822, 0.0409521161875, 0.0404330274434, 0.0399125309876, \
    0.0393906098197, 0.0388672464844, 0.0383424230521, 0.0378161210995, \
    0.037288321689, 0.0367590053466, 0.0362281520387, 0.0356957411476, \
    0.0351617514458, 0.034626161068, 0.0340889474822, 0.0335500874589, \
    0.033009557038, 0.032467331494, 0.0319233852988, 0.0313776920821, \
    0.0308302245895, 0.0302809546372, 0.0297298530646, 0.0291768896823, \
    0.0286220332182, 0.0280652512583, 0.0275065101844, 0.0269457751062, \
    0.02638300979, 0.0258181765805, 0.0252512363179, 0.0246821482486, \
    0.0241108699283, 0.0235373571186, 0.0229615636755, 0.0223834414285, \
    0.0218029400512, 0.0212200069209, 0.0206345869682, 0.0200466225144, \
    0.0194560530967, 0.0188628152806, 0.0182668424588, 0.0176680646372, \
    0.0170664082066, 0.016461795704, 0.0158541455627, 0.015243371858, \
    0.0146293840521, 0.0140120867521, 0.0133913794939, 0.0127671565806, \
    0.0121393070128, 0.0115077145716, 0.0108722581496, 0.0102328124764, \
    0.00958924947315, 0.00894144061242, 0.00828926090091, 0.00763259551896, \
    0.00697135089651, 0.00630547338383, 0.00563498133279, 0.00496002177703, \
    0.00428097439553, 0.00359865177269, 0.00291471045349, 0.00223256762114, \
    0.00155968193081 ])

ncell = array([
    0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, \
    2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, \
    5, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 7, 7, 8, 8, \
    8, 8, 8, 8, 8, 9, 9, 9, 9, 9, 9, 9, 10, 10, 10, 10, 10, 10, 10, 11, \
    11, 11, 11, 11, 11, 12, 12, 12, 12, 12, 12, 12, 13, 13, 13, 13, 13, 13, 13, 14, \
    14, 14, 14, 14, 14, 15, 15, 15, 15, 15, 15, 15, 16, 16, 16, 16, 16, 16, 17, 17, \
    17, 17, 17, 17, 17, 18, 18, 18, 18, 18, 18, 19, 19, 19, 19, 19, 19, 20, 20, 20, \
    20, 20, 20, 20, 21, 21, 21, 21, 21, 21, 22, 22, 22, 22, 22, 22, 23, 23, 23, 23, \
    23, 23, 24, 24, 24, 24, 24, 24, 25, 25, 25, 25, 25, 25, 26, 26, 26, 26, 26, 26, \
    27, 27, 27, 27, 27, 27, 28, 28, 28, 28, 28, 28, 29, 29, 29, 29, 29, 29, 30, 30, \
    30, 30, 30, 30, 31, 31, 31, 31, 31, 31, 32, 32, 32, 32, 32, 32, 33, 33, 33, 33, \
    33, 34, 34, 34, 34, 34, 34, 35, 35, 35, 35, 35, 35, 36, 36, 36, 36, 36, 37, 37, \
    37, 37, 37, 37, 38, 38, 38, 38, 38, 39, 39, 39, 39, 39, 39, 40, 40, 40, 40, 40, \
    40, 41, 41, 41, 41, 41, 42, 42, 42, 42, 42, 43, 43, 43, 43, 43, 43, 44, 44, 44, \
    44, 44, 45, 45, 45, 45, 45, 46, 46, 46, 46, 46, 46, 47, 47, 47, 47, 47, 48, 48, \
    48, 48, 48, 49, 49, 49, 49, 49, 50, 50, 50, 50, 50, 50, 51, 51, 51, 51, 51, 52, \
    52, 52, 52, 52, 53, 53, 53, 53, 53, 54, 54, 54, 54, 54, 55, 55, 55, 55, 55, 56, \
    56, 56, 56, 56, 57, 57, 57, 57, 57, 58, 58, 58, 58, 58, 59, 59, 59, 59, 59, 60, \
    60, 60, 60, 60, 61, 61, 61, 61, 61, 62, 62, 62, 62, 63, 63, 63, 63, 63, 64, 64, \
    64, 64, 64, 65, 65, 65, 65, 65, 66, 66, 66, 66, 66, 67, 67, 67, 67, 68, 68, 68, \
    68, 68, 69, 69, 69, 69, 69, 70, 70, 70, 70, 71, 71, 71, 71, 71, 72, 72, 72, 72, \
    72, 73, 73, 73, 73, 74, 74, 74, 74, 74, 75, 75, 75, 75, 76, 76, 76, 76, 76, 77, \
    77, 77, 77, 78, 78, 78, 78, 78, 79, 79, 79, 79, 80, 80, 80, 80, 80, 81, 81, 81, \
    81, 82, 82, 82, 82, 83, 83, 83, 83, 83, 84, 84, 84, 84, 85, 85, 85, 85, 86, 86, \
    86, 86, 86, 87, 87, 87, 87, 88, 88, 88, 88, 89, 89, 89, 89, 89, 90, 90, 90, 90, \
    91, 91, 91, 91, 92, 92, 92, 92, 93, 93, 93, 93, 94, 94, 94, 94, 95, 95, 95, 95, \
    95, 96, 96, 96, 96, 97, 97, 97, 97, 98, 98, 98, 98, 99, 99, 99, 99, 100, 100, 100, \
    100, 101, 101, 101, 101, 102, 102, 102, 102, 103, 103, 103, 103, 104, 104, 104, 104, 105, 105, 105, \
    105, 106, 106, 106, 106, 107, 107, 107, 107, 108, 108, 108, 108, 109, 109, 109, 109, 110, 110, 110, \
    110, 111, 111, 111, 111, 112, 112, 112, 113, 113, 113, 113, 114, 114, 114, 114, 115, 115, 115, 115, \
    116, 116, 116, 116, 117, 117, 117, 117, 118, 118, 118, 119, 119, 119, 119, 120, 120, 120, 120, 121, \
    121, 121, 121, 122, 122, 122, 123, 123, 123, 123, 124, 124, 124, 124, 125, 125, 125, 126, 126, 126, \
    126, 127, 127, 127, 127, 128, 128, 128, 129, 129, 129, 129, 130, 130, 130, 130, 131, 131, 131, 132, \
    132, 132, 132, 133, 133, 133, 134, 134, 134, 134, 135, 135, 135, 136, 136, 136, 136, 137, 137, 137, \
    137, 138, 138, 138, 139, 139, 139, 139, 140, 140, 140, 141, 141, 141, 141, 142, 142, 142, 143, 143, \
    143, 144, 144, 144, 144, 145, 145, 145, 146, 146, 146, 146, 147, 147, 147, 148, 148, 148, 148, 149, \
    149, 149, 150, 150, 150, 151, 151, 151, 151, 152, 152, 152, 153, 153, 153, 154, 154, 154, 154, 155, \
    155, 155, 156, 156, 156, 157, 157, 157, 157, 158, 158, 158, 159, 159, 159, 160, 160, 160, 160, 161, \
    161, 161, 162, 162, 162, 163, 163, 163, 164, 164, 164, 164, 165, 165, 165, 166, 166, 166, 167, 167, \
    167, 168, 168, 168, 169, 169, 169, 169, 170, 170, 170, 171, 171, 171, 172, 172, 172, 173, 173, 173, \
    174, 174, 174, 175, 175, 175, 176, 176, 176, 176, 177, 177, 177, 178, 178, 178, 179, 179, 179, 180, \
    180, 180, 181, 181, 181, 182, 182, 182, 183, 183, 183, 184, 184, 184, 185, 185, 185, 186, 186, 186, \
    187, 187, 187, 188, 188, 188, 189, 189, 189, 190, 190, 190, 191, 191, 191, 192, 192, 192, 193, 193, \
    193, 194, 194, 194, 195, 195, 195, 196, 196, 196, 197, 197, 197, 198, 198, 198, 199, 199, 199, 200, \
    200, 200, 201, 201, 201, 202, 202, 202, 203, 203, 203, 204, 204, 204, 205, 205, 206, 206, 206, 207, \
    207, 207, 208, 208, 208, 209, 209, 209, 210, 210, 210, 211, 211, 211, 212, 212, 213, 213, 213, 214, \
    214, 214, 215, 215, 215, 216, 216, 216, 217, 217, 217, 218, 218, 219, 219, 219, 220, 220, 220, 221, \
    221, 221, 222, 222, 223, 223, 223, 224, 224, 224, 225, 225, 225, 226, 226, 227, 227, 227, 228, 228, \
    228, 229, 229, 229, 230, 230, 231, 231, 231, 232, 232, 232, 233, 233, 234, 234, 234, 235, 235, 235, \
    236, 236, 237, 237, 237, 238, 238, 238, 239, 239, 240, 240, 240, 241, 241, 241, 242, 242, 243, 243, \
    243, 244, 244, 244, 245, 245, 246, 246, 246, 247, 247, 248, 248, 248, 249, 249, 249, 250, 250, 251, \
    251, 251, 252, 252, 253, 253, 253, 254, 254, 254, 255, 255, 256, 256, 256, 257, 257, 258, 258, 258, \
    259, 259, 260, 260, 260, 261, 261, 262, 262, 262, 263, 263, 264, 264, 264, 265, 265, 266, 266, 266, \
    267, 267, 268, 268, 268, 269, 269, 270, 270, 270, 271, 271, 272, 272, 272, 273, 273, 274, 274, 274, \
    275, 275, 276, 276, 276, 277, 277, 278, 278, 278, 279, 279, 280, 280, 280, 281, 281, 282, 282, 283, \
    283, 283, 284, 284, 285, 285, 285, 286, 286, 287, 287, 288, 288, 288, 289, 289, 290, 290, 290, 291, \
    291, 292, 292, 293, 293, 293, 294, 294, 295, 295, 296, 296, 296, 297, 297, 298, 298, 298, 299, 299, \
    300, 300, 301, 301, 301, 302, 302, 303, 303, 304, 304, 304, 305, 305, 306, 306, 307, 307, 307, 308, \
    308, 309, 309, 310, 310, 311, 311, 311, 312, 312, 313, 313, 314, 314, 314, 315, 315, 316, 316, 317, \
    317, 318, 318, 318, 319, 319, 320, 320, 321, 321, 322, 322, 322, 323, 323, 324, 324, 325, 325, 326, \
    326, 326, 327, 327, 328, 328, 329, 329, 330, 330, 330, 331, 331, 332, 332, 333, 333, 334, 334, 335, \
    335, 335, 336, 336, 337, 337, 338, 338, 339, 339, 340, 340, 340, 341, 341, 342, 342, 343, 343, 344, \
    344, 345, 345, 346, 346, 346, 347, 347, 348, 348, 349, 349, 350, 350, 351, 351, 352, 352, 353, 353, \
    353, 354, 354, 355, 355, 356, 356, 357, 357, 358, 358, 359, 359, 360, 360, 361, 361, 361, 362, 362, \
    363, 363, 364, 364, 365, 365, 366, 366, 367, 367, 368, 368, 369, 369, 370, 370, 371, 371, 371, 372, \
    372, 373, 373, 374, 374, 375, 375, 376, 376, 377, 377, 378, 378, 379, 379, 380, 380, 381, 381, 382, \
    382, 383, 383, 384, 384, 385, 385, 386, 386, 387, 387, 388, 388, 389, 389, 390, 390, 391, 391, 392, \
    392, 393, 393, 394, 394, 395, 395, 396, 396, 397, 397, 398, 398, 399, 399, 400, 400, 401, 401, 402, \
    402, 403, 403, 404, 404, 405, 405, 406, 406, 407, 407, 408, 408, 409, 409, 410, 410, 411, 411, 412, \
    412, 413, 413, 414, 414, 415, 415, 416, 416, 417, 417, 418, 418, 419, 419, 420, 420, 421, 421, 422, \
    423, 423, 424, 424, 425, 425, 426, 426, 427, 427, 428, 428, 429, 429, 430, 430, 431, 431, 432, 432, \
    433, 433, 434, 435, 435, 436, 436, 437, 437, 438, 438, 439, 439, 440, 440, 441, 441, 442, 442, 443, \
    444, 444, 445, 445, 446, 446, 447, 447, 448, 448, 449, 449, 450, 450, 451, 452, 452, 453, 453, 454, \
    454, 455, 455, 456, 456, 457, 458, 458, 459, 459, 460, 460, 461, 461, 462, 462, 463, 464, 464, 465, \
    465, 466, 466, 467, 467, 468, 468, 469, 470, 470, 471, 471, 472, 472, 473, 473, 474, 475, 475, 476, \
    476, 477, 477, 478, 478, 479, 480, 480, 481, 481, 482, 482, 483, 483, 484, 485, 485, 486, 486, 487, \
    487, 488, 488, 489, 490, 490, 491, 491, 492, 492, 493, 494, 494, 495, 495, 496, 496, 497, 498, 498, \
    499, 499, 500, 500, 501, 502, 502, 503, 503, 504, 504, 505, 506, 506, 507, 507, 508, 508, 509, 510, \
    510, 511, 511, 512, 512, 513, 514, 514, 515, 515, 516, 517, 517, 518, 518, 519, 519, 520, 521, 521, \
    522, 522, 523, 524, 524, 525, 525, 526, 526, 527, 528, 528, 529, 529, 530, 531, 531, 532, 532, 533, \
    534, 534, 535, 535, 536, 537, 537, 538, 538, 539, 539, 540, 541, 541, 542, 542, 543, 544, 544, 545, \
    545, 546, 547, 547, 548, 548, 549, 550, 550, 551, 551, 552, 553, 553, 554, 555, 555, 556, 556, 557, \
    558, 558, 559, 559, 560, 561, 561, 562, 562, 563, 564, 564, 565, 565, 566, 567, 567, 568, 569, 569, \
    570, 570, 571, 572, 572, 573, 573, 574, 575, 575, 576, 577, 577, 578, 578, 579, 580, 580, 581, 582, \
    582, 583, 583, 584, 585, 585, 586, 586, 587, 588, 588, 589, 590, 590, 591, 591, 592, 593, 593, 594, \
    595, 595, 596, 597, 597, 598, 598, 599, 600, 600, 601, 602, 602, 603, 603, 604, 605, 605, 606, 607, \
    607, 608, 609, 609, 610, 610, 611, 612, 612, 613, 614, 614, 615, 616, 616, 617, 618, 618, 619, 619, \
    620, 621, 621, 622, 623, 623, 624, 625, 625, 626, 627, 627, 628, 629, 629, 630, 630, 631, 632, 632, \
    633, 634, 634, 635, 636, 636, 637, 638, 638, 639, 640, 640, 641, 642, 642, 643, 644, 644, 645, 646, \
    646, 647, 647, 648, 649, 649, 650, 651, 651, 652, 653, 653, 654, 655, 655, 656, 657, 657, 658, 659, \
    659, 660, 661, 661, 662, 663, 663, 664, 665, 665, 666, 667, 667, 668, 669, 669, 670, 671, 671, 672, \
    673, 674, 674, 675, 676, 676, 677, 678, 678, 679, 680, 680, 681, 682, 682, 683, 684, 684, 685, 686, \
    686, 687, 688, 688, 689, 690, 690, 691, 692, 693, 693, 694, 695, 695, 696, 697, 697, 698, 699, 699, \
    700, 701, 701, 702, 703, 704, 704, 705, 706, 706, 707, 708, 708, 709, 710, 710, 711, 712, 713, 713, \
    714, 715, 715, 716, 717, 717, 718, 719, 719, 720, 721, 722, 722, 723, 724, 724, 725, 726, 726, 727, \
    728, 729, 729, 730, 731, 731, 732, 733, 734, 734, 735, 736, 736, 737, 738, 738, 739, 740, 741, 741, \
    742, 743, 743, 744, 745, 746, 746, 747, 748, 748, 749, 750, 751, 751, 752, 753, 753, 754, 755, 756, \
    756, 757, 758, 758, 759, 760, 761, 761, 762, 763, 763, 764, 765, 766, 766, 767, 768, 769, 769, 770, \
    771, 771, 772, 773, 774, 774, 775, 776, 777, 777, 778, 779, 779, 780, 781, 782, 782, 783, 784, 785, \
    785, 786, 787, 787, 788, 789, 790, 790, 791, 792, 793, 793, 794, 795, 796, 796, 797, 798, 798, 799, \
    800, 801, 801, 802, 803, 804, 804, 805, 806, 807, 807, 808, 809, 810, 810, 811, 812, 813, 813, 814, \
    815, 816, 816, 817, 818, 819, 819, 820, 821, 822, 822, 823, 824, 825, 825, 826, 827, 828, 828, 829, \
    830, 831, 831, 832, 833, 834, 834, 835, 836, 837, 837, 838, 839, 840, 840, 841, 842, 843, 843, 844, \
    845, 846, 846, 847, 848, 849, 849, 850, 851, 852, 853, 853, 854, 855, 856, 856, 857, 858, 859, 859, \
    860, 861, 862, 862, 863, 864, 865, 866, 866, 867, 868, 869, 869, 870, 871, 872, 872, 873, 874, 875, \
    876, 876, 877, 878, 879, 879, 880, 881, 882, 883, 883, 884, 885, 886, 886, 887, 888, 889, 890, 890, \
    891, 892, 893, 893, 894, 895, 896, 897, 897, 898, 899, 900, 900, 901, 902, 903, 904, 904, 905, 906, \
    907, 908, 908, 909, 910, 911, 911, 912, 913, 914, 915, 915, 916, 917, 918, 919, 919, 920, 921, 922, \
    923, 923, 924, 925, 926, 927, 927, 928, 929, 930, 931, 931, 932, 933, 934, 935, 935, 936, 937, 938, \
    939, 939, 940, 941, 942, 943, 943, 944, 945, 946, 947, 947, 948, 949, 950, 951, 951, 952, 953, 954, \
    955, 955, 956, 957, 958, 959, 959, 960, 961, 962, 963, 963, 964, 965, 966, 967, 968, 968, 969, 970, \
    971, 972, 972, 973, 974, 975, 976, 976, 977, 978, 979, 980, 981, 981, 982, 983, 984, 985, 985, 986, \
    987, 988, 989, 990, 990, 991, 992, 993, 994, 994, 995, 996, 997, 998, 999, 999, 1000, 1001, 1002, 1003, \
    1004, 1004, 1005, 1006, 1007, 1008, 1008, 1009, 1010, 1011, 1012, 1013, 1013, 1014, 1015, 1016, 1017, 1018, 1018, 1019, \
    1020, 1021, 1022, 1023, 1023, 1024, 1025, 1026, 1027, 1028, 1028, 1029, 1030, 1031, 1032, 1033, 1033, 1034, 1035, 1036, \
    1037, 1038, 1038, 1039, 1040, 1041, 1042, 1043, 1044, 1044, 1045, 1046, 1047, 1048, 1049, 1049, 1050, 1051, 1052, 1053, \
    1054, 1054, 1055, 1056, 1057, 1058, 1059, 1060, 1060, 1061, 1062, 1063, 1064, 1065, 1065, 1066, 1067, 1068, 1069, 1070, \
    1071, 1071, 1072, 1073, 1074, 1075, 1076, 1077, 1077, 1078, 1079, 1080, 1081, 1082, 1082, 1083, 1084, 1085, 1086, 1087, \
    1088, 1088, 1089, 1090, 1091, 1092, 1093, 1094, 1094, 1095, 1096, 1097, 1098, 1099, 1100, 1100, 1101, 1102, 1103, 1104, \
    1105, 1106, 1107, 1107, 1108, 1109, 1110, 1111, 1112, 1113, 1113, 1114, 1115, 1116, 1117, 1118, 1119, 1119, 1120, 1121, \
    1122, 1123, 1124, 1125, 1126, 1126, 1127, 1128, 1129, 1130, 1131, 1132, 1133, 1133, 1134, 1135, 1136, 1137, 1138, 1139, \
    1139, 1140, 1141, 1142, 1143, 1144, 1145, 1146, 1146, 1147, 1148, 1149, 1150, 1151, 1152, 1153, 1153, 1154, 1155, 1156, \
    1157, 1158, 1159, 1160, 1161, 1161, 1162, 1163, 1164, 1165, 1166, 1167, 1168, 1168, 1169, 1170, 1171, 1172, 1173, 1174, \
    1175, 1176, 1176, 1177, 1178, 1179, 1180, 1181, 1182, 1183, 1183, 1184, 1185, 1186, 1187, 1188, 1189, 1190, 1191, 1191, \
    1192, 1193, 1194, 1195, 1196, 1197, 1198, 1199, 1199, 1200, 1201, 1202, 1203, 1204, 1205, 1206, 1207, 1208, 1208, 1209, \
    1210, 1211, 1212, 1213, 1214, 1215, 1216, 1216, 1217, 1218, 1219, 1220, 1221, 1222, 1223, 1224, 1225, 1225, 1226, 1227, \
    1228, 1229, 1230, 1231, 1232, 1233, 1234, 1234, 1235, 1236, 1237, 1238, 1239, 1240, 1241, 1242, 1243, 1243, 1244, 1245, \
    1246, 1247, 1248, 1249, 1250, 1251, 1252, 1253, 1253, 1254, 1255, 1256, 1257, 1258, 1259, 1260, 1261, 1262, 1263, 1263, \
    1264, 1265, 1266, 1267, 1268, 1269, 1270, 1271, 1272, 1273, 1273, 1274, 1275, 1276, 1277, 1278, 1279, 1280, 1281, 1282, \
    1283, 1283, 1284, 1285, 1286, 1287, 1288, 1289, 1290, 1291, 1292, 1293, 1294, 1294, 1295, 1296, 1297, 1298, 1299, 1300, \
    1301, 1302, 1303, 1304, 1305, 1305, 1306, 1307, 1308, 1309, 1310, 1311, 1312, 1313, 1314, 1315, 1316, 1317, 1317, 1318, \
    1319, 1320, 1321, 1322, 1323, 1324, 1325, 1326, 1327, 1328, 1329, 1329, 1330, 1331, 1332, 1333, 1334, 1335, 1336, 1337, \
    1338, 1339, 1340, 1341, 1342, 1342, 1343, 1344, 1345, 1346, 1347, 1348, 1349, 1350, 1351, 1352, 1353, 1354, 1355, 1356, \
    1356, 1357, 1358, 1359, 1360, 1361, 1362, 1363, 1364, 1365, 1366, 1367, 1368, 1369, 1370, 1370, 1371, 1372, 1373, 1374, \
    1375, 1376, 1377, 1378, 1379, 1380, 1381, 1382, 1383, 1384, 1385, 1385, 1386, 1387, 1388, 1389, 1390, 1391, 1392, 1393, \
    1394, 1395, 1396, 1397, 1398, 1399, 1400, 1401, 1401, 1402, 1403, 1404, 1405, 1406, 1407, 1408, 1409, 1410, 1411, 1412, \
    1413, 1414, 1415, 1416, 1417, 1417, 1418, 1419, 1420, 1421, 1422, 1423, 1424, 1425, 1426, 1427, 1428, 1429, 1430, 1431, \
    1432, 1433, 1434, 1435, 1435, 1436, 1437, 1438, 1439, 1440, 1441, 1442, 1443, 1444, 1445, 1446, 1447, 1448, 1449, 1450, \
    1451, 1452, 1453, 1454, 1455, 1455, 1456, 1457, 1458, 1459, 1460, 1461, 1462, 1463, 1464, 1465, 1466, 1467, 1468, 1469, \
    1470, 1471, 1472, 1473, 1474, 1475, 1476, 1476, 1477, 1478, 1479, 1480, 1481, 1482, 1483, 1484, 1485, 1486, 1487, 1488, \
    1489, 1490, 1491, 1492, 1493, 1494, 1495, 1496, 1497, 1498, 1499, 1500, 1500, 1501, 1502, 1503, 1504, 1505, 1506, 1507, \
    1508, 1509, 1510, 1511, 1512, 1513, 1514, 1515, 1516, 1517, 1518, 1519, 1520, 1521, 1522, 1523, 1524, 1525, 1526, 1526, \
    1527, 1528, 1529, 1530, 1531, 1532, 1533, 1534, 1535, 1536, 1537, 1538, 1539, 1540, 1541, 1542, 1543, 1544, 1545, 1546, \
    1547, 1548, 1549, 1550, 1551, 1552, 1553, 1554, 1555, 1556, 1556, 1557, 1558, 1559, 1560, 1561, 1562, 1563, 1564, 1565, \
    1566, 1567, 1568, 1569, 1570, 1571, 1572, 1573, 1574, 1575, 1576, 1577, 1578, 1579, 1580, 1581, 1582, 1583, 1584, 1585, \
    1586, 1587, 1588, 1589, 1590, 1591, 1592, 1592, 1593, 1594, 1595, 1596, 1597, 1598, 1599, 1600, 1601, 1602, 1603, 1604, \
    1605, 1606, 1607, 1608, 1609, 1610, 1611, 1612, 1613, 1614, 1615, 1616, 1617, 1618, 1619, 1620, 1621, 1622, 1623, 1624, \
    1625, 1626, 1627, 1628, 1629, 1630, 1631, 1632, 1633, 1634, 1635, 1636, 1637, 1637, 1638, 1639, 1640, 1641, 1642, 1643, \
    1644, 1645, 1646, 1647, 1648, 1649, 1650, 1651, 1652, 1653, 1654, 1655, 1656, 1657, 1658, 1659, 1660, 1661, 1662, 1663, \
    1664, 1665, 1666, 1667, 1668, 1669, 1670, 1671, 1672, 1673, 1674, 1675, 1676, 1677, 1678, 1679, 1680, 1681, 1682, 1683, \
    1684, 1685, 1686, 1687, 1688, 1689, 1690, 1691, 1692, 1693, 1694, 1695, 1696, 1697, 1698, 1699, 1700, 1701, 1702, 1702, \
    1703, 1704, 1705, 1706, 1707, 1708, 1709, 1710, 1711, 1712, 1713, 1714, 1715, 1716, 1717, 1718, 1719, 1720, 1721, 1722, \
    1723, 1724, 1725, 1726, 1727, 1728, 1729, 1730, 1731, 1732, 1733, 1734, 1735, 1736, 1737, 1738, 1739, 1740, 1741, 1742, \
    1743, 1744, 1745, 1746, 1747, 1748, 1749, 1750, 1751, 1752, 1753, 1754, 1755, 1756, 1757, 1758, 1759, 1760, 1761, 1762, \
    1763, 1764, 1765, 1766, 1767, 1768, 1769, 1770, 1771, 1772, 1773, 1774, 1775, 1776, 1777, 1778, 1779, 1780, 1781, 1782, \
    1783, 1784, 1785, 1786, 1787, 1788, 1789, 1790, 1791, 1792, 1793, 1794, 1795, 1796, 1797, 1798, 1799, 1800, 1801, 1802, \
    1803, 1804, 1805, 1806, 1807, 1808, 1809, 1810, 1811, 1812, 1813, 1814, 1815, 1816, 1817, 1818, 1819, 1820, 1821, 1822, \
    1823, 1824, 1825, 1826, 1827, 1828, 1829, 1830, 1831, 1832, 1833, 1834, 1835, 1836, 1837, 1838, 1839, 1840, 1841, 1842, \
    1843, 1844, 1845, 1846, 1847, 1848, 1849, 1850, 1851, 1852, 1853, 1854, 1855, 1856, 1857, 1858, 1859, 1860, 1861, 1862, \
    1863, 1864, 1865, 1866, 1867, 1868, 1869, 1870, 1871, 1872, 1873, 1874, 1875, 1876, 1877, 1878, 1879, 1880, 1881, 1882, \
    1883, 1884, 1885, 1886, 1887, 1888, 1889, 1890, 1891, 1892, 1893, 1894, 1895, 1896, 1897, 1898, 1899, 1900, 1901, 1902, \
    1903, 1904, 1905, 1906, 1907, 1908, 1909, 1910, 1911, 1912, 1913, 1914, 1915, 1916, 1917, 1918, 1919, 1920, 1921, 1922, \
    1923, 1924, 1925, 1926, 1927, 1928, 1929, 1930, 1931, 1932, 1933, 1934, 1935, 1936, 1937, 1938, 1939, 1940, 1941, 1942, \
    1943, 1944, 1945, 1946, 1947, 1948, 1949, 1950, 1951, 1952, 1953, 1954, 1955, 1955, 1956, 1957, 1958, 1959, 1960, 1961, \
    1962, 1963, 1964, 1965, 1966, 1967, 1968, 1969, 1970, 1971, 1972, 1973, 1974, 1975, 1976, 1977, 1978, 1979, 1980, 1981, \
    1982, 1983, 1984, 1985, 1986, 1987, 1988, 1989, 1990, 1991, 1992, 1993, 1994, 1995, 1996, 1997, 1998, 1999, 2000, 2001, \
    2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, \
    2022, 2023, 2024, 2025, 2026, 2027, 2028, 2029, 2030, 2031, 2032, 2033, 2034, 2035, 2036, 2037, 2038, 2039, 2040, 2041, \
    2042, 2043, 2044, 2045, 2046, 2047, 2048, 2049, 2050, 2051, 2052, 2053, 2054, 2055, 2056, 2057, 2058, 2059, 2060, 2061, \
    2062, 2063, 2064, 2065, 2066, 2067, 2068, 2069, 2070, 2071, 2072, 2073, 2074, 2075, 2076, 2077, 2078, 2079, 2080, 2081, \
    2082, 2083, 2084, 2085, 2086, 2087, 2088, 2089, 2090, 2091, 2092, 2093, 2094, 2095, 2096, 2097, 2098, 2099, 2100, 2101, \
    2102, 2103, 2104, 2105, 2106, 2107, 2108, 2109, 2110, 2111, 2112, 2113, 2114, 2115, 2116, 2117, 2118, 2119, 2120, 2121, \
    2122, 2123, 2124, 2125, 2126, 2127, 2128, 2129, 2130, 2131, 2132, 2133, 2134, 2135, 2136, 2137, 2138, 2139, 2140, 2141, \
    2142, 2143, 2144, 2145, 2146, 2147, 2148, 2149, 2150, 2151, 2152, 2153, 2154, 2155, 2156, 2157, 2158, 2159, 2160, 2161, \
    2162, 2163, 2164, 2165, 2166, 2167, 2168, 2169, 2170, 2171, 2172, 2173, 2174, 2175, 2176, 2177, 2178, 2179, 2180, 2181, \
    2182, 2183, 2184, 2185, 2186, 2187, 2188, 2189, 2190, 2191, 2192, 2193, 2194, 2195, 2196, 2197, 2198, 2199, 2200, 2201, \
    2202, 2203, 2204, 2205, 2205, 2206, 2207, 2208, 2209, 2210, 2211, 2212, 2213, 2214, 2215, 2216, 2217, 2218, 2219, 2220, \
    2221, 2222, 2223, 2224, 2225, 2226, 2227, 2228, 2229, 2230, 2231, 2232, 2233, 2234, 2235, 2236, 2237, 2238, 2239, 2240, \
    2241, 2242, 2243, 2244, 2245, 2246, 2247, 2248, 2249, 2250, 2251, 2252, 2253, 2254, 2255, 2256, 2257, 2258, 2259, 2260, \
    2261, 2262, 2263, 2264, 2265, 2266, 2267, 2268, 2269, 2270, 2270, 2271, 2272, 2273, 2274, 2275, 2276, 2277, 2278, 2279, \
    2280, 2281, 2282, 2283, 2284, 2285, 2286, 2287, 2288, 2289, 2290, 2291, 2292, 2293, 2294, 2295, 2296, 2297, 2298, 2299, \
    2300, 2301, 2302, 2303, 2304, 2305, 2306, 2307, 2308, 2309, 2310, 2311, 2312, 2313, 2314, 2315, 2315, 2316, 2317, 2318, \
    2319, 2320, 2321, 2322, 2323, 2324, 2325, 2326, 2327, 2328, 2329, 2330, 2331, 2332, 2333, 2334, 2335, 2336, 2337, 2338, \
    2339, 2340, 2341, 2342, 2343, 2344, 2345, 2346, 2347, 2348, 2349, 2350, 2351, 2351, 2352, 2353, 2354, 2355, 2356, 2357, \
    2358, 2359, 2360, 2361, 2362, 2363, 2364, 2365, 2366, 2367, 2368, 2369, 2370, 2371, 2372, 2373, 2374, 2375, 2376, 2377, \
    2378, 2379, 2380, 2381, 2381, 2382, 2383, 2384, 2385, 2386, 2387, 2388, 2389, 2390, 2391, 2392, 2393, 2394, 2395, 2396, \
    2397, 2398, 2399, 2400, 2401, 2402, 2403, 2404, 2405, 2406, 2407, 2407, 2408, 2409, 2410, 2411, 2412, 2413, 2414, 2415, \
    2416, 2417, 2418, 2419, 2420, 2421, 2422, 2423, 2424, 2425, 2426, 2427, 2428, 2429, 2430, 2431, 2431, 2432, 2433, 2434, \
    2435, 2436, 2437, 2438, 2439, 2440, 2441, 2442, 2443, 2444, 2445, 2446, 2447, 2448, 2449, 2450, 2451, 2452, 2452, 2453, \
    2454, 2455, 2456, 2457, 2458, 2459, 2460, 2461, 2462, 2463, 2464, 2465, 2466, 2467, 2468, 2469, 2470, 2471, 2472, 2472, \
    2473, 2474, 2475, 2476, 2477, 2478, 2479, 2480, 2481, 2482, 2483, 2484, 2485, 2486, 2487, 2488, 2489, 2490, 2490, 2491, \
    2492, 2493, 2494, 2495, 2496, 2497, 2498, 2499, 2500, 2501, 2502, 2503, 2504, 2505, 2506, 2506, 2507, 2508, 2509, 2510, \
    2511, 2512, 2513, 2514, 2515, 2516, 2517, 2518, 2519, 2520, 2521, 2522, 2522, 2523, 2524, 2525, 2526, 2527, 2528, 2529, \
    2530, 2531, 2532, 2533, 2534, 2535, 2536, 2537, 2537, 2538, 2539, 2540, 2541, 2542, 2543, 2544, 2545, 2546, 2547, 2548, \
    2549, 2550, 2551, 2551, 2552, 2553, 2554, 2555, 2556, 2557, 2558, 2559, 2560, 2561, 2562, 2563, 2564, 2565, 2565, 2566, \
    2567, 2568, 2569, 2570, 2571, 2572, 2573, 2574, 2575, 2576, 2577, 2578, 2578, 2579, 2580, 2581, 2582, 2583, 2584, 2585, \
    2586, 2587, 2588, 2589, 2590, 2590, 2591, 2592, 2593, 2594, 2595, 2596, 2597, 2598, 2599, 2600, 2601, 2602, 2602, 2603, \
    2604, 2605, 2606, 2607, 2608, 2609, 2610, 2611, 2612, 2613, 2613, 2614, 2615, 2616, 2617, 2618, 2619, 2620, 2621, 2622, \
    2623, 2624, 2624, 2625, 2626, 2627, 2628, 2629, 2630, 2631, 2632, 2633, 2634, 2634, 2635, 2636, 2637, 2638, 2639, 2640, \
    2641, 2642, 2643, 2644, 2644, 2645, 2646, 2647, 2648, 2649, 2650, 2651, 2652, 2653, 2654, 2654, 2655, 2656, 2657, 2658, \
    2659, 2660, 2661, 2662, 2663, 2664, 2664, 2665, 2666, 2667, 2668, 2669, 2670, 2671, 2672, 2673, 2673, 2674, 2675, 2676, \
    2677, 2678, 2679, 2680, 2681, 2682, 2682, 2683, 2684, 2685, 2686, 2687, 2688, 2689, 2690, 2691, 2691, 2692, 2693, 2694, \
    2695, 2696, 2697, 2698, 2699, 2699, 2700, 2701, 2702, 2703, 2704, 2705, 2706, 2707, 2708, 2708, 2709, 2710, 2711, 2712, \
    2713, 2714, 2715, 2716, 2716, 2717, 2718, 2719, 2720, 2721, 2722, 2723, 2724, 2724, 2725, 2726, 2727, 2728, 2729, 2730, \
    2731, 2731, 2732, 2733, 2734, 2735, 2736, 2737, 2738, 2739, 2739, 2740, 2741, 2742, 2743, 2744, 2745, 2746, 2746, 2747, \
    2748, 2749, 2750, 2751, 2752, 2753, 2754, 2754, 2755, 2756, 2757, 2758, 2759, 2760, 2761, 2761, 2762, 2763, 2764, 2765, \
    2766, 2767, 2768, 2768, 2769, 2770, 2771, 2772, 2773, 2774, 2774, 2775, 2776, 2777, 2778, 2779, 2780, 2781, 2781, 2782, \
    2783, 2784, 2785, 2786, 2787, 2788, 2788, 2789, 2790, 2791, 2792, 2793, 2794, 2794, 2795, 2796, 2797, 2798, 2799, 2800, \
    2800, 2801, 2802, 2803, 2804, 2805, 2806, 2807, 2807, 2808, 2809, 2810, 2811, 2812, 2813, 2813, 2814, 2815, 2816, 2817, \
    2818, 2819, 2819, 2820, 2821, 2822, 2823, 2824, 2825, 2825, 2826, 2827, 2828, 2829, 2830, 2830, 2831, 2832, 2833, 2834, \
    2835, 2836, 2836, 2837, 2838, 2839, 2840, 2841, 2842, 2842, 2843, 2844, 2845, 2846, 2847, 2847, 2848, 2849, 2850, 2851, \
    2852, 2853, 2853, 2854, 2855, 2856, 2857, 2858, 2858, 2859, 2860, 2861, 2862, 2863, 2863, 2864, 2865, 2866, 2867, 2868, \
    2869, 2869, 2870, 2871, 2872, 2873, 2874, 2874, 2875, 2876, 2877, 2878, 2879, 2879, 2880, 2881, 2882, 2883, 2884, 2884, \
    2885, 2886, 2887, 2888, 2889, 2889, 2890, 2891, 2892, 2893, 2894, 2894, 2895, 2896, 2897, 2898, 2899, 2899, 2900, 2901, \
    2902, 2903, 2903, 2904, 2905, 2906, 2907, 2908, 2908, 2909, 2910, 2911, 2912, 2913, 2913, 2914, 2915, 2916, 2917, 2917, \
    2918, 2919, 2920, 2921, 2922, 2922, 2923, 2924, 2925, 2926, 2926, 2927, 2928, 2929, 2930, 2931, 2931, 2932, 2933, 2934, \
    2935, 2935, 2936, 2937, 2938, 2939, 2939, 2940, 2941, 2942, 2943, 2944, 2944, 2945, 2946, 2947, 2948, 2948, 2949, 2950, \
    2951, 2952, 2952, 2953, 2954, 2955, 2956, 2956, 2957, 2958, 2959, 2960, 2960, 2961, 2962, 2963, 2964, 2964, 2965, 2966, \
    2967, 2968, 2968, 2969, 2970, 2971, 2972, 2972, 2973, 2974, 2975, 2976, 2976, 2977, 2978, 2979, 2980, 2980, 2981, 2982, \
    2983, 2984, 2984, 2985, 2986, 2987, 2988, 2988, 2989, 2990, 2991, 2992, 2992, 2993, 2994, 2995, 2996, 2996, 2997, 2998, \
    2999, 2999, 3000, 3001, 3002, 3003, 3003, 3004, 3005, 3006, 3007, 3007, 3008, 3009, 3010, 3010, 3011, 3012, 3013, 3014, \
    3014, 3015, 3016, 3017, 3017, 3018, 3019, 3020, 3021, 3021, 3022, 3023, 3024, 3024, 3025, 3026, 3027, 3028, 3028, 3029, \
    3030, 3031, 3031, 3032, 3033, 3034, 3035, 3035, 3036, 3037, 3038, 3038, 3039, 3040, 3041, 3041, 3042, 3043, 3044, 3045, \
    3045, 3046, 3047, 3048, 3048, 3049, 3050, 3051, 3051, 3052, 3053, 3054, 3054, 3055, 3056, 3057, 3058, 3058, 3059, 3060, \
    3061, 3061, 3062, 3063, 3064, 3064, 3065, 3066, 3067, 3067, 3068, 3069, 3070, 3070, 3071, 3072, 3073, 3073, 3074, 3075, \
    3076, 3076, 3077, 3078, 3079, 3079, 3080, 3081, 3082, 3082, 3083, 3084, 3085, 3085, 3086, 3087, 3088, 3088, 3089, 3090, \
    3091, 3091, 3092, 3093, 3094, 3094, 3095, 3096, 3097, 3097, 3098, 3099, 3100, 3100, 3101, 3102, 3103, 3103, 3104, 3105, \
    3106, 3106, 3107, 3108, 3109, 3109, 3110, 3111, 3111, 3112, 3113, 3114, 3114, 3115, 3116, 3117, 3117, 3118, 3119, 3120, \
    3120, 3121, 3122, 3122, 3123, 3124, 3125, 3125, 3126, 3127, 3128, 3128, 3129, 3130, 3130, 3131, 3132, 3133, 3133, 3134, \
    3135, 3136, 3136, 3137, 3138, 3138, 3139, 3140, 3141, 3141, 3142, 3143, 3144, 3144, 3145, 3146, 3146, 3147, 3148, 3149, \
    3149, 3150, 3151, 3151, 3152, 3153, 3154, 3154, 3155, 3156, 3156, 3157, 3158, 3159, 3159, 3160, 3161, 3161, 3162, 3163, \
    3164, 3164, 3165, 3166, 3166, 3167, 3168, 3169, 3169, 3170, 3171, 3171, 3172, 3173, 3173, 3174, 3175, 3176, 3176, 3177, \
    3178, 3178, 3179, 3180, 3181, 3181, 3182, 3183, 3183, 3184, 3185, 3185, 3186, 3187, 3188, 3188, 3189, 3190, 3190, 3191, \
    3192, 3192, 3193, 3194, 3194, 3195, 3196, 3197, 3197, 3198, 3199, 3199, 3200, 3201, 3201, 3202, 3203, 3203, 3204, 3205, \
    3206, 3206, 3207, 3208, 3208, 3209, 3210, 3210, 3211, 3212, 3212, 3213, 3214, 3214, 3215, 3216, 3217, 3217, 3218, 3219, \
    3219, 3220, 3221, 3221, 3222, 3223, 3223, 3224, 3225, 3225, 3226, 3227, 3227, 3228, 3229, 3229, 3230, 3231, 3231, 3232, \
    3233, 3233, 3234, 3235, 3236, 3236, 3237, 3238, 3238, 3239, 3240, 3240, 3241, 3242, 3242, 3243, 3244, 3244, 3245, 3246, \
    3246, 3247, 3248, 3248, 3249, 3250, 3250, 3251, 3252, 3252, 3253, 3254, 3254, 3255, 3256, 3256, 3257, 3258, 3258, 3259, \
    3260, 3260, 3261, 3261, 3262, 3263, 3263, 3264, 3265, 3265, 3266, 3267, 3267, 3268, 3269, 3269, 3270, 3271, 3271, 3272, \
    3273, 3273, 3274, 3275, 3275, 3276, 3277, 3277, 3278, 3278, 3279, 3280, 3280, 3281, 3282, 3282, 3283, 3284, 3284, 3285, \
    3286, 3286, 3287, 3288, 3288, 3289, 3289, 3290, 3291, 3291, 3292, 3293, 3293, 3294, 3295, 3295, 3296, 3297, 3297, 3298, \
    3298, 3299, 3300, 3300, 3301, 3302, 3302, 3303, 3304, 3304, 3305, 3305, 3306, 3307, 3307, 3308, 3309, 3309, 3310, 3310, \
    3311, 3312, 3312, 3313, 3314, 3314, 3315, 3316, 3316, 3317, 3317, 3318, 3319, 3319, 3320, 3321, 3321, 3322, 3322, 3323, \
    3324, 3324, 3325, 3325, 3326, 3327, 3327, 3328, 3329, 3329, 3330, 3330, 3331, 3332, 3332, 3333, 3334, 3334, 3335, 3335, \
    3336, 3337, 3337, 3338, 3338, 3339, 3340, 3340, 3341, 3342, 3342, 3343, 3343, 3344, 3345, 3345, 3346, 3346, 3347, 3348, \
    3348, 3349, 3349, 3350, 3351, 3351, 3352, 3352, 3353, 3354, 3354, 3355, 3356, 3356, 3357, 3357, 3358, 3359, 3359, 3360, \
    3360, 3361, 3362, 3362, 3363, 3363, 3364, 3365, 3365, 3366, 3366, 3367, 3368, 3368, 3369, 3369, 3370, 3370, 3371, 3372, \
    3372, 3373, 3373, 3374, 3375, 3375, 3376, 3376, 3377, 3378, 3378, 3379, 3379, 3380, 3381, 3381, 3382, 3382, 3383, 3383, \
    3384, 3385, 3385, 3386, 3386, 3387, 3388, 3388, 3389, 3389, 3390, 3390, 3391, 3392, 3392, 3393, 3393, 3394, 3395, 3395, \
    3396, 3396, 3397, 3397, 3398, 3399, 3399, 3400, 3400, 3401, 3401, 3402, 3403, 3403, 3404, 3404, 3405, 3405, 3406, 3407, \
    3407, 3408, 3408, 3409, 3409, 3410, 3411, 3411, 3412, 3412, 3413, 3413, 3414, 3415, 3415, 3416, 3416, 3417, 3417, 3418, \
    3419, 3419, 3420, 3420, 3421, 3421, 3422, 3422, 3423, 3424, 3424, 3425, 3425, 3426, 3426, 3427, 3427, 3428, 3429, 3429, \
    3430, 3430, 3431, 3431, 3432, 3432, 3433, 3434, 3434, 3435, 3435, 3436, 3436, 3437, 3437, 3438, 3439, 3439, 3440, 3440, \
    3441, 3441, 3442, 3442, 3443, 3443, 3444, 3445, 3445, 3446, 3446, 3447, 3447, 3448, 3448, 3449, 3449, 3450, 3451, 3451, \
    3452, 3452, 3453, 3453, 3454, 3454, 3455, 3455, 3456, 3457, 3457, 3458, 3458, 3459, 3459, 3460, 3460, 3461, 3461, 3462, \
    3462, 3463, 3463, 3464, 3465, 3465, 3466, 3466, 3467, 3467, 3468, 3468, 3469, 3469, 3470, 3470, 3471, 3471, 3472, 3472, \
    3473, 3474, 3474, 3475, 3475, 3476, 3476, 3477, 3477, 3478, 3478, 3479, 3479, 3480, 3480, 3481, 3481, 3482, 3482, 3483, \
    3483, 3484, 3484, 3485, 3486, 3486, 3487, 3487, 3488, 3488, 3489, 3489, 3490, 3490, 3491, 3491, 3492, 3492, 3493, 3493, \
    3494, 3494, 3495, 3495, 3496, 3496, 3497, 3497, 3498, 3498, 3499, 3499, 3500, 3500, 3501, 3501, 3502, 3502, 3503, 3503, \
    3504, 3504, 3505, 3505, 3506, 3506, 3507, 3507, 3508, 3508, 3509, 3509, 3510, 3510, 3511, 3511, 3512, 3512, 3513, 3513, \
    3514, 3514, 3515, 3515, 3516, 3516, 3517, 3517, 3518, 3518, 3519, 3519, 3520, 3520, 3521, 3521, 3522, 3522, 3523, 3523, \
    3524, 3524, 3525, 3525, 3526, 3526, 3527, 3527, 3528, 3528, 3529, 3529, 3530, 3530, 3531, 3531, 3532, 3532, 3533, 3533, \
    3534, 3534, 3535, 3535, 3536, 3536, 3536, 3537, 3537, 3538, 3538, 3539, 3539, 3540, 3540, 3541, 3541, 3542, 3542, 3543, \
    3543, 3544, 3544, 3545, 3545, 3546, 3546, 3546, 3547, 3547, 3548, 3548, 3549, 3549, 3550, 3550, 3551, 3551, 3552, 3552, \
    3553, 3553, 3554, 3554, 3554, 3555, 3555, 3556, 3556, 3557, 3557, 3558, 3558, 3559, 3559, 3560, 3560, 3561, 3561, 3561, \
    3562, 3562, 3563, 3563, 3564, 3564, 3565, 3565, 3566, 3566, 3567, 3567, 3567, 3568, 3568, 3569, 3569, 3570, 3570, 3571, \
    3571, 3572, 3572, 3572, 3573, 3573, 3574, 3574, 3575, 3575, 3576, 3576, 3577, 3577, 3577, 3578, 3578, 3579, 3579, 3580, \
    3580, 3581, 3581, 3581, 3582, 3582, 3583, 3583, 3584, 3584, 3585, 3585, 3585, 3586, 3586, 3587, 3587, 3588, 3588, 3589, \
    3589, 3589, 3590, 3590, 3591, 3591, 3592, 3592, 3593, 3593, 3593, 3594, 3594, 3595, 3595, 3596, 3596, 3596, 3597, 3597, \
    3598, 3598, 3599, 3599, 3600, 3600, 3600, 3601, 3601, 3602, 3602, 3603, 3603, 3603, 3604, 3604, 3605, 3605, 3606, 3606, \
    3606, 3607, 3607, 3608, 3608, 3609, 3609, 3609, 3610, 3610, 3611, 3611, 3611, 3612, 3612, 3613, 3613, 3614, 3614, 3614, \
    3615, 3615, 3616, 3616, 3617, 3617, 3617, 3618, 3618, 3619, 3619, 3619, 3620, 3620, 3621, 3621, 3622, 3622, 3622, 3623, \
    3623, 3624, 3624, 3624, 3625, 3625, 3626, 3626, 3627, 3627, 3627, 3628, 3628, 3629, 3629, 3629, 3630, 3630, 3631, 3631, \
    3631, 3632, 3632, 3633, 3633, 3633, 3634, 3634, 3635, 3635, 3635, 3636, 3636, 3637, 3637, 3637, 3638, 3638, 3639, 3639, \
    3639, 3640, 3640, 3641, 3641, 3641, 3642, 3642, 3643, 3643, 3643, 3644, 3644, 3645, 3645, 3645, 3646, 3646, 3647, 3647, \
    3647, 3648, 3648, 3649, 3649, 3649, 3650, 3650, 3651, 3651, 3651, 3652, 3652, 3653, 3653, 3653, 3654, 3654, 3654, 3655, \
    3655, 3656, 3656, 3656, 3657, 3657, 3658, 3658, 3658, 3659, 3659, 3659, 3660, 3660, 3661, 3661, 3661, 3662, 3662, 3663, \
    3663, 3663, 3664, 3664, 3664, 3665, 3665, 3666, 3666, 3666, 3667, 3667, 3667, 3668, 3668, 3669, 3669, 3669, 3670, 3670, \
    3670, 3671, 3671, 3672, 3672, 3672, 3673, 3673, 3673, 3674, 3674, 3675, 3675, 3675, 3676, 3676, 3676, 3677, 3677, 3678, \
    3678, 3678, 3679, 3679, 3679, 3680, 3680, 3680, 3681, 3681, 3682, 3682, 3682, 3683, 3683, 3683, 3684, 3684, 3684, 3685, \
    3685, 3686, 3686, 3686, 3687, 3687, 3687, 3688, 3688, 3688, 3689, 3689, 3690, 3690, 3690, 3691, 3691, 3691, 3692, 3692, \
    3692, 3693, 3693, 3693, 3694, 3694, 3694, 3695, 3695, 3696, 3696, 3696, 3697, 3697, 3697, 3698, 3698, 3698, 3699, 3699, \
    3699, 3700, 3700, 3700, 3701, 3701, 3701, 3702, 3702, 3703, 3703, 3703, 3704, 3704, 3704, 3705, 3705, 3705, 3706, 3706, \
    3706, 3707, 3707, 3707, 3708, 3708, 3708, 3709, 3709, 3709, 3710, 3710, 3710, 3711, 3711, 3711, 3712, 3712, 3712, 3713, \
    3713, 3713, 3714, 3714, 3714, 3715, 3715, 3715, 3716, 3716, 3716, 3717, 3717, 3717, 3718, 3718, 3718, 3719, 3719, 3719, \
    3720, 3720, 3720, 3721, 3721, 3721, 3722, 3722, 3722, 3723, 3723, 3723, 3724, 3724, 3724, 3725, 3725, 3725, 3726, 3726, \
    3726, 3727, 3727, 3727, 3728, 3728, 3728, 3729, 3729, 3729, 3730, 3730, 3730, 3731, 3731, 3731, 3731, 3732, 3732, 3732, \
    3733, 3733, 3733, 3734, 3734, 3734, 3735, 3735, 3735, 3736, 3736, 3736, 3737, 3737, 3737, 3738, 3738, 3738, 3738, 3739, \
    3739, 3739, 3740, 3740, 3740, 3741, 3741, 3741, 3742, 3742, 3742, 3743, 3743, 3743, 3743, 3744, 3744, 3744, 3745, 3745, \
    3745, 3746, 3746, 3746, 3747, 3747, 3747, 3747, 3748, 3748, 3748, 3749, 3749, 3749, 3750, 3750, 3750, 3750, 3751, 3751, \
    3751, 3752, 3752, 3752, 3753, 3753, 3753, 3753, 3754, 3754, 3754, 3755, 3755, 3755, 3756, 3756, 3756, 3756, 3757, 3757, \
    3757, 3758, 3758, 3758, 3759, 3759, 3759, 3759, 3760, 3760, 3760, 3761, 3761, 3761, 3761, 3762, 3762, 3762, 3763, 3763, \
    3763, 3763, 3764, 3764, 3764, 3765, 3765, 3765, 3766, 3766, 3766, 3766, 3767, 3767, 3767, 3768, 3768, 3768, 3768, 3769, \
    3769, 3769, 3770, 3770, 3770, 3770, 3771, 3771, 3771, 3771, 3772, 3772, 3772, 3773, 3773, 3773, 3773, 3774, 3774, 3774, \
    3775, 3775, 3775, 3775, 3776, 3776, 3776, 3777, 3777, 3777, 3777, 3778, 3778, 3778, 3778, 3779, 3779, 3779, 3780, 3780, \
    3780, 3780, 3781, 3781, 3781, 3781, 3782, 3782, 3782, 3783, 3783, 3783, 3783, 3784, 3784, 3784, 3784, 3785, 3785, 3785, \
    3786, 3786, 3786, 3786, 3787, 3787, 3787, 3787, 3788, 3788, 3788, 3788, 3789, 3789, 3789, 3790, 3790, 3790, 3790, 3791, \
    3791, 3791, 3791, 3792, 3792, 3792, 3792, 3793, 3793, 3793, 3793, 3794, 3794, 3794, 3794, 3795, 3795, 3795, 3796, 3796, \
    3796, 3796, 3797, 3797, 3797, 3797, 3798, 3798, 3798, 3798, 3799, 3799, 3799, 3799, 3800, 3800, 3800, 3800, 3801, 3801, \
    3801, 3801, 3802, 3802, 3802, 3802, 3803, 3803, 3803, 3803, 3804, 3804, 3804, 3804, 3805, 3805, 3805, 3805, 3806, 3806, \
    3806, 3806, 3807, 3807, 3807, 3807, 3808, 3808, 3808, 3808, 3809, 3809, 3809, 3809, 3810, 3810, 3810, 3810, 3811, 3811, \
    3811, 3811, 3812, 3812, 3812, 3812, 3812, 3813, 3813, 3813, 3813, 3814, 3814, 3814, 3814, 3815, 3815, 3815, 3815, 3816, \
    3816, 3816, 3816, 3817, 3817, 3817, 3817, 3818, 3818, 3818, 3818, 3818, 3819, 3819, 3819, 3819, 3820, 3820, 3820, 3820, \
    3821, 3821, 3821, 3821, 3821, 3822, 3822, 3822, 3822, 3823, 3823, 3823, 3823, 3824, 3824, 3824, 3824, 3824, 3825, 3825, \
    3825, 3825, 3826, 3826, 3826, 3826, 3827, 3827, 3827, 3827, 3827, 3828, 3828, 3828, 3828, 3829, 3829, 3829, 3829, 3829, \
    3830, 3830, 3830, 3830, 3831, 3831, 3831, 3831, 3831, 3832, 3832, 3832, 3832, 3833, 3833, 3833, 3833, 3833, 3834, 3834, \
    3834, 3834, 3835, 3835, 3835, 3835, 3835, 3836, 3836, 3836, 3836, 3836, 3837, 3837, 3837, 3837, 3838, 3838, 3838, 3838, \
    3838, 3839, 3839, 3839, 3839, 3839, 3840, 3840, 3840, 3840, 3841, 3841, 3841, 3841, 3841, 3842, 3842, 3842, 3842, 3842, \
    3843, 3843, 3843, 3843, 3843, 3844, 3844, 3844, 3844, 3844, 3845, 3845, 3845, 3845, 3846, 3846, 3846, 3846, 3846, 3847, \
    3847, 3847, 3847, 3847, 3848, 3848, 3848, 3848, 3848, 3849, 3849, 3849, 3849, 3849, 3850, 3850, 3850, 3850, 3850, 3851, \
    3851, 3851, 3851, 3851, 3852, 3852, 3852, 3852, 3852, 3853, 3853, 3853, 3853, 3853, 3854, 3854, 3854, 3854, 3854, 3855, \
    3855, 3855, 3855, 3855, 3856, 3856, 3856, 3856, 3856, 3857, 3857, 3857, 3857, 3857, 3857, 3858, 3858, 3858, 3858, 3858, \
    3859, 3859, 3859, 3859, 3859, 3860, 3860, 3860, 3860, 3860, 3861, 3861, 3861, 3861, 3861, 3861, 3862, 3862, 3862, 3862, \
    3862, 3863, 3863, 3863, 3863, 3863, 3864, 3864, 3864, 3864, 3864, 3864, 3865, 3865, 3865, 3865, 3865, 3866, 3866, 3866, \
    3866, 3866, 3867, 3867, 3867, 3867, 3867, 3867, 3868, 3868, 3868, 3868, 3868, 3868, 3869, 3869, 3869, 3869, 3869, 3870, \
    3870, 3870, 3870, 3870, 3870, 3871, 3871, 3871, 3871, 3871, 3872, 3872, 3872, 3872, 3872, 3872, 3873, 3873, 3873, 3873, \
    3873, 3873, 3874, 3874, 3874, 3874, 3874, 3875, 3875, 3875, 3875, 3875, 3875, 3876, 3876, 3876, 3876, 3876, 3876, 3877, \
    3877, 3877, 3877, 3877, 3877, 3878, 3878, 3878, 3878, 3878, 3878, 3879, 3879, 3879, 3879, 3879, 3879, 3880, 3880, 3880, \
    3880, 3880, 3880, 3881, 3881, 3881, 3881, 3881, 3881, 3882, 3882, 3882, 3882, 3882, 3882, 3883, 3883, 3883, 3883, 3883, \
    3883, 3884, 3884, 3884, 3884, 3884, 3884, 3885, 3885, 3885, 3885, 3885, 3885, 3886, 3886, 3886, 3886, 3886, 3886, 3887, \
    3887, 3887, 3887, 3887, 3887, 3887, 3888, 3888, 3888, 3888, 3888, 3888, 3889, 3889, 3889, 3889, 3889, 3889, 3890, 3890, \
    3890, 3890, 3890, 3890, 3890, 3891, 3891, 3891, 3891, 3891, 3891, 3892, 3892, 3892, 3892, 3892, 3892, 3892, 3893, 3893, \
    3893, 3893, 3893, 3893, 3894, 3894, 3894, 3894, 3894, 3894, 3894, 3895, 3895, 3895, 3895, 3895, 3895, 3895, 3896, 3896, \
    3896, 3896, 3896, 3896, 3897, 3897, 3897, 3897, 3897, 3897, 3897, 3898, 3898, 3898, 3898, 3898, 3898, 3898, 3899, 3899, \
    3899, 3899, 3899, 3899, 3899, 3900, 3900, 3900, 3900, 3900, 3900, 3900, 3901, 3901, 3901, 3901, 3901, 3901, 3901, 3902, \
    3902, 3902, 3902, 3902, 3902, 3902, 3903, 3903, 3903, 3903, 3903, 3903, 3903, 3904, 3904, 3904, 3904, 3904, 3904, 3904, \
    3905, 3905, 3905, 3905, 3905, 3905, 3905, 3906, 3906, 3906, 3906, 3906, 3906, 3906, 3906, 3907, 3907, 3907, 3907, 3907, \
    3907, 3907, 3908, 3908, 3908, 3908, 3908, 3908, 3908, 3908, 3909, 3909, 3909, 3909, 3909, 3909, 3909, 3910, 3910, 3910, \
    3910, 3910, 3910, 3910, 3910, 3911, 3911, 3911, 3911, 3911, 3911, 3911, 3912, 3912, 3912, 3912, 3912, 3912, 3912, 3912, \
    3913, 3913, 3913, 3913, 3913, 3913, 3913, 3913, 3914, 3914, 3914, 3914, 3914, 3914, 3914, 3914, 3915, 3915, 3915, 3915, \
    3915, 3915, 3915, 3915, 3916, 3916, 3916, 3916, 3916, 3916, 3916, 3916, 3917, 3917, 3917, 3917, 3917, 3917, 3917, 3917, \
    3918, 3918, 3918, 3918, 3918, 3918, 3918, 3918, 3919, 3919, 3919, 3919, 3919, 3919, 3919, 3919, 3919, 3920, 3920, 3920, \
    3920, 3920, 3920, 3920, 3920, 3921, 3921, 3921, 3921, 3921, 3921, 3921, 3921, 3922, 3922, 3922, 3922, 3922, 3922, 3922, \
    3922, 3922, 3923, 3923, 3923, 3923, 3923, 3923, 3923, 3923, 3923, 3924, 3924, 3924, 3924, 3924, 3924, 3924, 3924, 3925, \
    3925, 3925, 3925, 3925, 3925, 3925, 3925, 3925, 3926, 3926, 3926, 3926, 3926, 3926, 3926, 3926, 3926, 3927, 3927, 3927, \
    3927, 3927, 3927, 3927, 3927, 3927, 3928, 3928, 3928, 3928, 3928, 3928, 3928, 3928, 3928, 3929, 3929, 3929, 3929, 3929, \
    3929, 3929, 3929, 3929, 3929, 3930, 3930, 3930, 3930, 3930, 3930, 3930, 3930, 3930, 3931, 3931, 3931, 3931, 3931, 3931, \
    3931, 3931, 3931, 3931, 3932, 3932, 3932, 3932, 3932, 3932, 3932, 3932, 3932, 3933, 3933, 3933, 3933, 3933, 3933, 3933, \
    3933, 3933, 3933, 3934, 3934, 3934, 3934, 3934, 3934, 3934, 3934, 3934, 3934, 3935, 3935, 3935, 3935, 3935, 3935, 3935, \
    3935, 3935, 3935, 3936, 3936, 3936, 3936, 3936, 3936, 3936, 3936, 3936, 3936, 3937, 3937, 3937, 3937, 3937, 3937, 3937, \
    3937, 3937, 3937, 3938, 3938, 3938, 3938, 3938, 3938, 3938, 3938, 3938, 3938, 3938, 3939, 3939, 3939, 3939, 3939, 3939, \
    3939, 3939, 3939, 3939, 3940, 3940, 3940, 3940, 3940, 3940, 3940, 3940, 3940, 3940, 3940, 3941, 3941, 3941, 3941, 3941, \
    3941, 3941, 3941, 3941, 3941, 3941, 3942, 3942, 3942, 3942, 3942, 3942, 3942, 3942, 3942, 3942, 3942, 3943, 3943, 3943, \
    3943, 3943, 3943, 3943, 3943, 3943, 3943, 3943, 3944, 3944, 3944, 3944, 3944, 3944, 3944, 3944, 3944, 3944, 3944, 3945, \
    3945, 3945, 3945, 3945, 3945, 3945, 3945, 3945, 3945, 3945, 3945, 3946, 3946, 3946, 3946, 3946, 3946, 3946, 3946, 3946, \
    3946, 3946, 3947, 3947, 3947, 3947, 3947, 3947, 3947, 3947, 3947, 3947, 3947, 3947, 3948, 3948, 3948, 3948, 3948, 3948, \
    3948, 3948, 3948, 3948, 3948, 3948, 3949, 3949, 3949, 3949, 3949, 3949, 3949, 3949, 3949, 3949, 3949, 3949, 3949, 3950, \
    3950, 3950, 3950, 3950, 3950, 3950, 3950, 3950, 3950, 3950, 3950, 3951, 3951, 3951, 3951, 3951, 3951, 3951, 3951, 3951, \
    3951, 3951, 3951, 3951, 3952, 3952, 3952, 3952, 3952, 3952, 3952, 3952, 3952, 3952, 3952, 3952, 3952, 3953, 3953, 3953, \
    3953, 3953, 3953, 3953, 3953, 3953, 3953, 3953, 3953, 3953, 3954, 3954, 3954, 3954, 3954, 3954, 3954, 3954, 3954, 3954, \
    3954, 3954, 3954, 3955, 3955, 3955, 3955, 3955, 3955, 3955, 3955, 3955, 3955, 3955, 3955, 3955, 3955, 3956, 3956, 3956, \
    3956, 3956, 3956, 3956, 3956, 3956, 3956, 3956, 3956, 3956, 3956, 3957, 3957, 3957, 3957, 3957, 3957, 3957, 3957, 3957, \
    3957, 3957, 3957, 3957, 3957, 3958, 3958, 3958, 3958, 3958, 3958, 3958, 3958, 3958, 3958, 3958, 3958, 3958, 3958, 3958, \
    3959, 3959, 3959, 3959, 3959, 3959, 3959, 3959, 3959, 3959, 3959, 3959, 3959, 3959, 3959, 3960, 3960, 3960, 3960, 3960, \
    3960, 3960, 3960, 3960, 3960, 3960, 3960, 3960, 3960, 3960, 3961, 3961, 3961, 3961, 3961, 3961, 3961, 3961, 3961, 3961, \
    3961, 3961, 3961, 3961, 3961, 3962, 3962, 3962, 3962, 3962, 3962, 3962, 3962, 3962, 3962, 3962, 3962, 3962, 3962, 3962, \
    3962, 3963, 3963, 3963, 3963, 3963, 3963, 3963, 3963, 3963, 3963, 3963, 3963, 3963, 3963, 3963, 3963, 3964, 3964, 3964, \
    3964, 3964, 3964, 3964, 3964, 3964, 3964, 3964, 3964, 3964, 3964, 3964, 3964, 3964, 3965, 3965, 3965, 3965, 3965, 3965, \
    3965, 3965, 3965, 3965, 3965, 3965, 3965, 3965, 3965, 3965, 3965, 3966, 3966, 3966, 3966, 3966, 3966, 3966, 3966, 3966, \
    3966, 3966, 3966, 3966, 3966, 3966, 3966, 3966, 3967, 3967, 3967, 3967, 3967, 3967, 3967, 3967, 3967, 3967, 3967, 3967, \
    3967, 3967, 3967, 3967, 3967, 3967, 3968, 3968, 3968, 3968, 3968, 3968, 3968, 3968, 3968, 3968, 3968, 3968, 3968, 3968, \
    3968, 3968, 3968, 3968, 3969, 3969, 3969, 3969, 3969, 3969, 3969, 3969, 3969, 3969, 3969, 3969, 3969, 3969, 3969, 3969, \
    3969, 3969, 3969, 3970, 3970, 3970, 3970, 3970, 3970, 3970, 3970, 3970, 3970, 3970, 3970, 3970, 3970, 3970, 3970, 3970, \
    3970, 3970, 3971, 3971, 3971, 3971, 3971, 3971, 3971, 3971, 3971, 3971, 3971, 3971, 3971, 3971, 3971, 3971, 3971, 3971, \
    3971, 3971, 3972, 3972, 3972, 3972, 3972, 3972, 3972, 3972, 3972, 3972, 3972, 3972, 3972, 3972, 3972, 3972, 3972, 3972, \
    3972, 3972, 3972, 3973, 3973, 3973, 3973, 3973, 3973, 3973, 3973, 3973, 3973, 3973, 3973, 3973, 3973, 3973, 3973, 3973, \
    3973, 3973, 3973, 3973, 3974, 3974, 3974, 3974, 3974, 3974, 3974, 3974, 3974, 3974, 3974, 3974, 3974, 3974, 3974, 3974, \
    3974, 3974, 3974, 3974, 3974, 3974, 3975, 3975, 3975, 3975, 3975, 3975, 3975, 3975, 3975, 3975, 3975, 3975, 3975, 3975, \
    3975, 3975, 3975, 3975, 3975, 3975, 3975, 3975, 3976, 3976, 3976, 3976, 3976, 3976, 3976, 3976, 3976, 3976, 3976, 3976, \
    3976, 3976, 3976, 3976, 3976, 3976, 3976, 3976, 3976, 3976, 3976, 3976, 3977, 3977, 3977, 3977, 3977, 3977, 3977, 3977, \
    3977, 3977, 3977, 3977, 3977, 3977, 3977, 3977, 3977, 3977, 3977, 3977, 3977, 3977, 3977, 3977, 3978, 3978, 3978, 3978, \
    3978, 3978, 3978, 3978, 3978, 3978, 3978, 3978, 3978, 3978, 3978, 3978, 3978, 3978, 3978, 3978, 3978, 3978, 3978, 3978, \
    3978, 3979, 3979, 3979, 3979, 3979, 3979, 3979, 3979, 3979, 3979, 3979, 3979, 3979, 3979, 3979, 3979, 3979, 3979, 3979, \
    3979, 3979, 3979, 3979, 3979, 3979, 3979, 3980, 3980, 3980, 3980, 3980, 3980, 3980, 3980, 3980, 3980, 3980, 3980, 3980, \
    3980, 3980, 3980, 3980, 3980, 3980, 3980, 3980, 3980, 3980, 3980, 3980, 3980, 3980, 3981, 3981, 3981, 3981, 3981, 3981, \
    3981, 3981, 3981, 3981, 3981, 3981, 3981, 3981, 3981, 3981, 3981, 3981, 3981, 3981, 3981, 3981, 3981, 3981, 3981, 3981, \
    3981, 3981, 3981, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, \
    3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3982, 3983, 3983, 3983, 3983, 3983, 3983, 3983, \
    3983, 3983, 3983, 3983, 3983, 3983, 3983, 3983, 3983, 3983, 3983, 3983, 3983, 3983, 3983, 3983, 3983, 3983, 3983, 3983, \
    3983, 3983, 3983, 3983, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, \
    3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3984, 3985, 3985, 3985, \
    3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, \
    3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3985, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, \
    3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, \
    3986, 3986, 3986, 3986, 3986, 3986, 3986, 3986, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, \
    3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, 3987, \
    3987, 3987, 3987, 3987, 3987, 3987, 3987, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, \
    3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, \
    3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3988, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, \
    3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, \
    3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3989, 3990, 3990, 3990, 3990, 3990, 3990, 3990, \
    3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, \
    3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, 3990, \
    3990, 3990, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, \
    3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, \
    3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3991, 3992, 3992, 3992, 3992, 3992, 3992, \
    3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, \
    3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, \
    3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3992, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, \
    3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, \
    3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, \
    3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3993, 3994, 3994, 3994, 3994, 3994, 3994, \
    3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, \
    3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, \
    3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, 3994, \
    3994, 3994, 3994, 3994, 3994, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, \
    3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, \
    3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, \
    3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, 3995, \
    3995, 3995, 3995, 3995, 3995, 3995, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, \
    3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, \
    3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, \
    3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, \
    3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3996, 3997, \
    3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, \
    3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, \
    3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, \
    3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, \
    3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, \
    3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3997, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, \
    3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, \
    3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, \
    3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, \
    3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, \
    3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, \
    3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, 3998, \
    3998, 3998, 3998, 3998, 3998, 3998, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, \
    3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, \
    3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, \
    3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, \
    3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, \
    3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, \
    3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, \
    3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, \
    3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, 3999, \
    3999, 3999, 3999, 3999, 3999, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, \
    4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, \
    4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, \
    4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, \
    4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, \
    4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, \
    4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, \
    4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, \
    4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, \
    4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, \
    4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, \
    4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, \
    4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, 4000, \
    4000 ])
