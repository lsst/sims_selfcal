from __future__ import print_function
from __future__ import absolute_import
from builtins import str
from builtins import range
from builtins import object
import os
import numpy
from scipy import interpolate, fftpack
from .PowerSpectrum import PowerSpectrum
from pylab import rms_flat

class Clouds(object):    
    def __init__(self, ws, s):
        # set the half-diagonal size of the 2D Fourier space equal to the maximum frequency of the 1D power spectrum
        self.windowsize = ws/numpy.sqrt(2.)
        # set the sampling directly in the real space : same sampling than the correlation function (arbitrary)
        self.sampling = s
        # and the spacing
        self.xstep = self.windowsize/numpy.float(self.sampling)

    def setupPowerSpectrum_SF(self):
        """Set up the power spectrum used to generate the clouds. """
        ps = PowerSpectrum(self.windowsize, self.sampling)
        ps.ComputeStructureFunction()
        self.correl2D = ps.getCorrel2D()
        
    def setupPowerSpectrum_Image(self):
        """Set up the power spectrum used to generate the clouds, when using an image as the base."""
        # Note that this is actually a different version of a power spectrum than the one from
        #  a raw 'power spectrum' above ... should really have a different name, as has different attributes.
        ps = PowerSpectrum(self.windowsize, self.sampling)
        self.powerSpec = ps.GetImPS()
        
        
    def DirectClouds(self, correl2D=None, randomSeed=None):
        """Directly compute clouds using random noise in real space"""
        # nothing to do with symetry, quarters shift, etc.
        # compute 2D power spectrum from 2D symetric correlation function
        if correl2D == None:
            correl2D = self.correl2D   # do this for backward compatibility
        PowerSpec2D = numpy.abs(fftpack.fft2(correl2D))
        # get a 2D random gaussian noise with rms = 1
        # If random seed is set, then set that within numpy (allows repeatable performance). 
        if randomSeed != None:
            numpy.random.seed(randomSeed)
        noise2D = numpy.random.normal(numpy.zeros(self.sampling*self.sampling), 1.).reshape(self.sampling, self.sampling)
        # a realization is given in Fourier space calculating tf(noise)*sqrt(powerspectum)
        fourierclouds = fftpack.fft2(noise2D)*numpy.sqrt(PowerSpec2D)
        # then, inverse Fourier transform to get clouds
        self.clouds = numpy.real(fftpack.ifft2(fourierclouds))

        # IS IT POSSIBLE THAT THIS FUNCTION (or a different one) COULD RETURN AN INTERPOLATION FUNCTION FOR THE CLOUD INSTEAD
        #  OF THE GRID OF CLOUD EXTINCTION VALUES?

    def CloudsFromImage(self, powerSpec=None, randomSeed=None, normfile=None):
        """Compute clouds based on frequency analysis of an IR image"""
        ## for this temp version sampling at 240 imperative (interpolation was too slow and removed for now)        
        # get power spectrum from an IR image - normalization for gray ext. see notes
        ## reference here !!
        # get a 2D random gaussien noise with rms = 1
        if powerSpec == None:
            powerSpec = self.powerSpec
        if randomSeed != None:
            numpy.random.seed(randomSeed)
        noise2D = numpy.random.normal(numpy.zeros(self.sampling*self.sampling), 1.).reshape(self.sampling, self.sampling)        
        # a realization is given in Fourier space calculating tf(noise)*sqrt(powerspectum)
        fourierclouds = fftpack.fft2(noise2D)*numpy.sqrt(powerSpec)
        # then, inverse Fourier transform to get clouds
        self.clouds = numpy.real(fftpack.ifft2(fourierclouds))
        # get 0 abs as minimum alteration of image  
        mins=[]
        maxs=[]
        for i in range(self.sampling):
            mins = numpy.append(mins, min(self.clouds[i,:]))
            maxs = numpy.append(maxs, max(self.clouds[i,:]))
        self.clouds = self.clouds - min(mins)
        ## correct for normalizations 
        if normfile == None:
            normfile = os.path.join(os.getenv('ATMOSPHERE_CLOUDS_DIR'), 'data/1104-batch1_im.txt')
            print(normfile)
        init_im = numpy.loadtxt(normfile)
        self.clouds = self.clouds/rms_flat(self.clouds)*rms_flat(init_im)
        ## will return an interpolation function next 


    def WriteClouds(self, filename):
        """Write clouds in a text file x y z"""
        f = open(filename, 'w')
        # only take 1/4 of the 2D real space (other 3/4 is only use for symetry of the correlation function)
        # but 4 fields of view can be taken separatly from one realization
        # !! DO NOT take the whole field of view because, clouds are correlated over larger distances due to the symetry !!
        for i in range(self.sampling/2):
            for j in range(self.sampling/2):
                f.write(str(i*self.xstep)+'\t'+str(j*self.xstep)+'\t'+str(real(self.clouds[i,j]))+'\n')
        f.close()

