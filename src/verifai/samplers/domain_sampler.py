
"""Samplers generating points in a Domain, possibly subject to specifications.
"""

### Exceptions pertaining to sampling

class SamplingError(Exception):
    """Exception raised if a Sampler is unable to produce a sample"""
    pass

### Exceptions pertaining to sampling termination

class TerminationException(Exception):
    """Exception raised if sampling has terminated,
    e.g. grid sampling and bayesian optimization"""
    pass

### Samplers defined over fixed Domains

## Abstract samplers

class DomainSampler:
    """Abstract sampler class"""

    def __init__(self, domain):
        self.domain = domain
        self.last_sample = None

    def getSample(self):
        """Generate the next sample, given the current distribution.

        Must return a pair consisting of the sample and arbitrary
        sampler-specific info, which will be passed to the `update`
        method after the sample is evaluated.
        """
        raise NotImplementedError('tried to use abstract Sampler')
    
    def update(self, sample, info, rho):
        """
        Use the provided sample and rho value to update the state of the sampler.

        Arguments:
            sample: the exact value generated by the sampler.
            info: any additional info needed to complete the update,
            such as the buckets that were sampled from for continuous samplers.
            rho: the result of the sample, returned by the falsifier.
        """
        pass

    def nextSample(self, feedback=None):
        """Generate the next sample, given feedback from the last sample."""
        if self.last_sample is not None and feedback is not None:
            self.update(self.last_sample, self.last_info, feedback)
        self.last_sample, self.last_info = self.getSample()
        return self.last_sample, self.last_info

    def getVector(self):
        raise NotImplementedError('tried to use abstract Sampler')

    def nextSample(self, feedback=None):
        """Generate the next sample, given feedback from the last sample."""
        if self.last_sample is not None and feedback is not None:
            self.update(self.last_sample, self.last_info, feedback)
        self.last_sample, self.last_info = self.getSample()
        return self.last_sample, self.last_info

    def __iter__(self):
        try:
            feedback = None
            while True:
                feedback = yield self.nextSample(feedback)
        except TerminationException:
            return

class ConstrainedSampler(DomainSampler):
    """Abstract DomainSampler constrained by a specification."""

    def __init__(self, domain, spec):
        super().__init__(domain)
        self.specification = spec

class SplitSampler(DomainSampler):
    """Sampler using different strategies for different types of domains"""

    def __init__(self, domain, samplers):
        super().__init__(domain)
        self.samplers = tuple(samplers)

    def getSample(self):
        samples, infos = [], []
        for sampler in self.samplers:
            sample, info = sampler.getSample()
            samples.append(sample)
            infos.append(info)
        return self.domain.rejoinPoints(*samples), infos

    def update(self, sample, info, rho):
        for sampler, i in zip(self.samplers, info):
            if i is not None:
                sampler.update(sample, i, rho)

    @classmethod
    def fromPartition(cls, domain, partition, defaultSampler=None):
        """Make a SplitSampler by partitioning a domain by predicates.

        The given partition should consist of a sequence of pairs of predicates
        and functions which return a sampler given a domain. The part of the
        domain satisfying the first predicate is given to the first function to
        make a sampler for it. The remaining part of the space is split along
        the second predicate, and so forth. If the partition is non-exhaustive
        (part of the domain does not satisfy any of the predicates), then an
        error is raised unless a default sampler is specified, in which case it
        is called with the remaining part of the space to make a sampler.

        This sampler this method returns has a samplersForPredicates attribute
        which indicates for the ith predicate which subsampler (or None)
        corresponds to its part of the domain. If a default sampler is used,
        the tuple has an extra last element for it.
        """
        samplers = []
        remaining = domain
        samplersForPredicates = [None for i in partition]
        for i, (predicate, makeSampler) in enumerate(partition):
            component, remaining = remaining.partition(predicate)
            if component:
                sampler = makeSampler(component)
                samplers.append(sampler)
                samplersForPredicates[i] = sampler
            if not remaining:
                break
        if remaining:
            if defaultSampler is None:
                raise RuntimeError('tried to make SplitSampler with'
                                   ' non-exhaustive partition')
            else:
                sampler = defaultSampler(remaining)
                samplers.append(sampler)
                samplersForPredicates.append(sampler)
        assert len(samplers) > 0
        sampler = cls(domain, samplers)
        sampler.samplersForPredicates = tuple(samplersForPredicates)
        return sampler

    @classmethod
    def fromPredicate(cls, domain, predicate, leftSampler, rightSampler):
        """Make a SplitSampler by splitting a domain by a single predicate."""
        return cls.fromPartition(domain,
                                 ((predicate, leftSampler),),
                                 rightSampler)

class BoxSampler(DomainSampler):
    """Samplers defined only over unit hyperboxes"""
    def __init__(self, domain):
        self.dimension = domain.standardizedDimension
        if not self.dimension >= 0:
            raise RuntimeError(f'{self.__class__.__name__} supports only'
                               ' continuous standardizable Domains')
        super().__init__(domain)
    
    def getSample(self):
        sample, info = self.getVector()
        return self.domain.unstandardize(sample), info

    def getVector(self):
        raise NotImplementedError('tried to use abstract BoxSampler')

    def nextVector(self, feedback=None):
        if self.last_sample is not None and feedback is not None:
            self.update(self.last_sample, self.last_info, feedback)
        return self.getVector()

class DiscreteBoxSampler(DomainSampler):
    """Samplers defined only over discrete hyperboxes"""
    def __init__(self, domain):
        self.intervals = domain.standardizedIntervals
        if not self.intervals:
            raise RuntimeError(f'{self.__class__.__name__} supports only'
                               ' discrete standardizable Domains')
        super().__init__(domain)

    def getSample(self):
        sample, info = self.getVector()
        return self.domain.unstandardize(sample), info

class IteratorSampler(DomainSampler):
    """Samplers defined using a generator function."""

    def __init__(self, domain, repeat=False):
        super().__init__(domain)
        self.repeat = repeat
        self.iterator = iter(self)

    def nextSample(self, feedback=None):
        try:
            return self.iterator.send(feedback)
        except StopIteration:
            if self.repeat:
                self.iterator = iter(self)
                return self.iterator.send(feedback)
            else:
                raise TerminationException from None

    def __iter__(self):
        raise NotImplementedError('tried to iterate abstract IteratorSampler')
