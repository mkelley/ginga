#
# astro/image.py -- Abstraction of an astronomical data image.
#
#[ Eric Jeschke (eric@naoj.org) --
#  Last edit: Wed Sep  5 18:15:38 HST 2012
#]
# Takeshi Inagaki
#
# Copyright (c) 2011-2012, Eric R. Jeschke.  All rights reserved.
# This is open-source software licensed under a BSD license.
# Please see the file LICENSE.txt for details.
#
import sys
import math
import time
import iqcalc
import wcs

import pyfits
import numpy

wcs_offset = 0.5

class CalcError(Exception):
    pass

class AstroImage(object):
    """
    Abstraction of an astronomical data (image).
    
    NOTE: this module is NOT thread-safe!
    """

    def __init__(self, data_np=None, metadata=None, wcsclass=None,
                 logger=None):
        if data_np == None:
            data_np = numpy.zeros((1, 1))
        self.data = data_np
        self.metadata = {}
        if not wcsclass:
            wcsclass = wcs.WCS
        self.wcs = wcsclass()
        if metadata:
            self.update_metadata(metadata)

        self.maximize_region()
        self.iqcalc = iqcalc.IQCalc(logger=logger)


    @property
    def width(self):
        # NOTE: numpy stores data in column-major layout
        return self.data.shape[1]
        
    @property
    def height(self):
        # NOTE: numpy stores data in column-major layout
        return self.data.shape[0]

    def load_hdu(self, hdu, naxispath=None):
        data = hdu.data
        if not naxispath:
            naxispath = ([0] * (len(data.shape)-2))

        for idx in naxispath:
            data = data[idx]
        self.set_data(data)

        # Load in FITS header
        self.update_keywords(hdu.header)
        # Preserve the ordering of the FITS keywords in the FITS file
        keyorder = [ key for key, val in hdu.header.items() ]
        self.set(keyorder=keyorder)

        # Try to make a wcs object on the header
        self.wcs.load_header(hdu.header)

    def load_file(self, filepath, numhdu=None, naxispath=None):
        self.set(path=filepath)
        fits_f = pyfits.open(filepath, 'readonly')

        # this seems to be necessary now for some fits files...
        try:
            fits_f.verify('fix')
        except Exception, e:
            raise CalcError("Error loading fits file '%s': %s" % (
                fitspath, str(e)))

        if numhdu == None:
            found_valid_hdu = False
            for i in range(len(fits_f)):
                hdu = fits_f[i]
                if hdu.data == None:
                    # compressed FITS file or non-pixel data hdu?
                    continue
                if not isinstance(hdu.data, numpy.ndarray):
                    # We need to open a numpy array
                    continue
                if len(hdu.data.shape) < 2:
                    # Don't know what to make of 1D data
                    continue
                # Looks good, let's try it
                found_valid_hdu = True
                break
            
            if not found_valid_hdu:
                raise CalcError("No data HDU found that Ginga can open in '%s'" % (
                    filepath))
        else:
            numhdu = fits_f[numhdu]
            
        self.load_hdu(hdu, naxispath=naxispath)
        
        fits_f.close()

    def get_size(self):
        return (self.width, self.height)
    
    def set_region(self, x1, y1, x2, y2):
        assert x1 >=0 and x1 < self.width, \
               CalcError("x1 value (%d) out of range (0..%d-1)" % (
                   x1, self.width))
        assert y1 >=0 and y1 < self.height, \
               CalcError("y1 value (%d) out of range (0..%d-1)" % (
                   y1, self.height))
        assert x2 >=0 and x2 < self.width, \
               CalcError("x2 value (%d) out of range (0..%d-1)" % (
                   x2, self.width))
        assert y2 >=0 and y2 < self.height, \
               CalcError("y2 value (%d) out of range (0..%d-1)" % (
                   y2, self.height))

        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    def set_compatible_region(self, x1, y1, x2, y2):
        """Sets the most compatible region consistent with the image size.
        Returns the region set."""
        (g1, h1, g2, h2) = self.get_max_region()
        u1 = min(max(g1, x1), x2)
        v1 = min(max(h1, y1), y2)
        u2 = min(g2, x2)
        v2 = min(h2, y2)
        self.set_region(u1, v1, u2, v2)
        return self.get_region()
        
    def copy_region(self, other):
        other.set_region(self.x1, self.y1, self.x2, self.y2)
        
    def get_max_region(self):
        return (0, 0, self.width-1, self.height-1)
        
    def maximize_region(self):
        self.set_region(0, 0, self.width-1, self.height-1)
        
    def get_region(self):
        return (self.x1, self.y1, self.x2, self.y2)
        
    def get_data(self):
        return self.data.copy()
        
    def get_metadata(self):
        return self.metadata.copy()
        
    def get(self, kwd, *args):
        if self.metadata.has_key(kwd):
            return self.metadata[kwd]
        else:
            # return a default if there is one
            if len(args) > 0:
                return args[0]
            raise KeyError(kwd)
        
    def get_list(self, *args):
        return map(self.get, args)
    
    def __getitem__(self, kwd):
        return self.metadata[kwd]
        
    def update(self, kwds):
        self.metadata.update(kwds)
        
    def set(self, **kwds):
        self.update(kwds)
        
    def __setitem__(self, kwd, value):
        self.metadata[kwd] = value
        
    def get_header(self, create=True):
        try:
            # By convention, the fits header is stored in a dictionary
            # under the metadata keyword 'header'
            hdr = self.metadata['header']
        except KeyError, e:
            if not create:
                raise e
            hdr = {}
            self.metadata['header'] = hdr
        return hdr
        
    def get_keyword(self, kwd, *args):
        """Get an item from the fits header, if any."""
        try:
            kwds = self.get_header()
            return kwds[kwd]
        except KeyError:
            # return a default if there is one
            if len(args) > 0:
                return args[0]
            raise KeyError(kwd)

    def get_keywords_list(self, *args):
        return map(self.get_keyword, args)
    
    def set_keyword(self, kwd, value, create=True):
        kwds = self.get_header(create=create)
        kwd = kwd.upper()
        if not create:
            prev = kwds[kwd]
        kwds[kwd] = value
        
    def update_keywords(self, keyDict):
        hdr = self.get_header()
        # Upcase all keywords
        for kwd, val in keyDict.items():
            hdr[kwd.upper()] = val

        # refresh WCS
        self.wcs.load_header(hdr)
        
    def set_keywords(self, **kwds):
        """Set an item in the fits header, if any."""
        return self.update_keywords(kwds)
        
    def _update_region(self):
        """Update region to reflect new size."""
        self.set_region(min(self.x1, self.width-1),
                        min(self.y1, self.height-1),
                        min(self.x2, self.width-1),
                        min(self.y2, self.height-1))

    def set_data(self, data_np, metadata=None, astype=None):
        """Use this method to SHARE (not copy) the incoming array.
        """
        if astype:
            self.data = data_np.astype(astype)
        else:
            self.data = data_np
        if metadata:
            self.update_metadata(metadata)
            
        self._update_region()
        
    def update_data(self, data_np, metadata=None, astype=None):
        """Use this method to make a private copy of the incoming array.
        """
        self.set_data(data_np.copy(), metadata=metadata,
                      astype=astype)
        
    def update_metadata(self, keyDict):
        for key, val in keyDict.items():
            self.metadata[key] = val

        # refresh the WCS
        header = self.get_header()
        self.wcs.load_header(header)

    def update_hdu(self, hdu, astype=None):
        self.update_data(hdu.data, astype=astype)
        self.update_keywords(hdu.header)

    def update_file(self, path, index=0, astype=None):
        fits_f = pyfits.open(path, 'readonly')
        self.update_hdu(fits_f[index], astype=astype)
        fits_f.close()

    def transfer(self, other, astype=None):
        other.update_data(self.data, astype=astype)
        other.update_metadata(self.metadata)
        self.copy_region(other)
        
    def copy(self, astype=None):
        other = AstroImage(self.data)
        self.transfer(other, astype=astype)
        return other
        
    def cutout_data(self, x1, y1, x2, y2, astype=None):
        """cut out data area based on coords. 
        """
        data = self.data[y1:y2, x1:x2]
        if astype:
            data = data.astype(astype)
        return data
  
    def cutout_adjust(self, x1, y1, x2, y2, astype=None):
        dx = x2 - x1
        dy = y2 - y1
        
        if x1 < 0:
            x1 = 0; x2 = dx
        else:
            if x2 >= self.width:
                x2 = self.width
                x1 = x2 - dx
                
        if y1 < 0:
            y1 = 0; y2 = dy
        else:
            if y2 >= self.height:
                y2 = self.height
                y1 = y2 - dy

        data = self.cutout_data(x1, y1, x2, y2, astype=astype)
        return (data, x1, y1, x2, y2)

    def cutout_radius(self, x, y, radius, astype=None):
        return self.cutout_adjust(x-radius, y-radius,
                                  x+radius+1, y+radius+1,
                                  astype=astype)

    def cutout_cross(self, x, y, radius):
        """Cut two data subarrays that have a center at (x, y) and with
        radius (radius) from (data).  Returns the starting pixel (x0, y0)
        of each cut and the respective arrays (xarr, yarr).
        """
        n = radius
        ht, wd = self.height, self.width
        x0, x1 = max(0, x-n), min(wd-1, x+n)
        y0, y1 = max(0, y-n), min(ht-1, y+n)
        xarr = self.data[y, x0:x1+1]
        yarr = self.data[y0:y1+1, x]
        return (x0, y0, xarr, yarr)


    def qualsize(self, x1=None, y1=None, x2=None, y2=None, radius=5,
                 bright_radius=2, threshold=None):
        if x1 == None:
            x1 = self.x1
            y1 = self.y1
            x2 = self.x2
            y2 = self.y2

        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        data = self.cutout_data(x1, y1, x2, y2, astype='float32')

        start_time = time.time()
        qs = self.iqcalc.pick_field(data, radius=radius,
                                    bright_radius=bright_radius,
                                    threshold=threshold)
        elapsed = time.time() - start_time
        print "e: obj=%f,%f fwhm=%f sky=%f bright=%f (%f sec)" % (
            qs.objx, qs.objy, qs.fwhm, qs.skylevel, qs.brightness, elapsed)
        
        # Add back in offsets into image to get correct values with respect
        # to the entire image
        qs.x += x1
        qs.y += y1
        qs.objx += x1
        qs.objy += y1

        return qs
     

    def create_fits(self):
        fits_f = pyfits.HDUList()
        hdu = pyfits.PrimaryHDU()
        data = self.data
        if sys.byteorder == 'little':
            data = data.byteswap()
        hdu.data = data

        deriver = self.get('deriver', None)
        if deriver:
            deriver.deriveAll(self)
            keylist = deriver.get_keylist()
        else:
            keylist = self.get('keyorder', None)

        header = self.get_header()

        if not keylist:
            keylist = header.keys()

        errlist = []
        for kwd in keylist:
            try:
                if deriver:
                    comment = deriver.get_comment(kwd)
                hdu.header.update(kwd, header[kwd], comment=comment)
            except Exception, e:
                errlist.append((kwd, str(e)))

        fits_f.append(hdu)
        return fits_f
    
    def write_fits(self, path, output_verify='fix'):
        fits_f = self.create_fits()
        return fits_f.writeto(path, output_verify=output_verify)
        
    def pixtoradec(self, x, y, format='deg', coords='data'):
        return self.wcs.pixtoradec(x, y, format=format, coords=coords)
    
    def radectopix(self, ra_deg, dec_deg, coords='data'):
        return self.wcs.radectopix(ra_deg, dec_deg, coords=coords)

    def dispos(self, dra0, decd0, dra, decd):
        """
        Source/credit: Skycat
        
        dispos computes distance and position angle solving a spherical 
        triangle (no approximations)
        INPUT        :coords in decimal degrees
        OUTPUT       :dist in arcmin, returns phi in degrees (East of North)
        AUTHOR       :a.p.martinez
        Parameters:
          dra0: center RA  decd0: center DEC  dra: point RA  decd: point DEC

        Returns:
          distance in arcmin
        """
        radian = 180.0/math.pi

        # coo transformed in radiants 
        alf = dra / radian
        alf0 = dra0 / radian
        del_ = decd / radian
        del0 = decd0 / radian

        sd0 = math.sin(del0)
        sd = math.sin(del_)
        cd0 = math.cos(del0)
        cd = math.cos(del_)
        cosda = math.cos(alf - alf0)
        cosd = sd0*sd+cd0*cd*cosda
        dist = math.acos(cosd)
        phi = 0.0
        if dist > 0.0000004:
            sind = math.sin(dist)
            cospa = (sd*cd0 - cd*sd0*cosda)/sind
            #if cospa > 1.0:
            #    cospa=1.0
            if math.fabs(cospa) > 1.0:
                # 2005-06-02: fix from awicenec@eso.org
                cospa = cospa/math.fabs(cospa) 
            sinpa = cd*math.sin(alf-alf0)/sind
            phi = math.acos(cospa)*radian
            if sinpa < 0.0:
                phi = 360.0-phi
        dist *= radian
        dist *= 60.0
        if decd0 == 90.0:
            phi = 180.0
        if decd0 == -90.0:
            phi = 0.0
        return (phi, dist)


    def deltaStarsRaDecDeg1(self, ra1_deg, dec1_deg, ra2_deg, dec2_deg):
        phi, dist = self.dispos(ra1_deg, dec1_deg, ra2_deg, dec2_deg)
        return wcs.arcsecToDeg(dist*60.0)

    def deltaStarsRaDecDeg2(self, ra1_deg, dec1_deg, ra2_deg, dec2_deg):
        ra1_rad = math.radians(ra1_deg)
        dec1_rad = math.radians(dec1_deg)
        ra2_rad = math.radians(ra2_deg)
        dec2_rad = math.radians(dec2_deg)
        
        sep_rad = math.acos(math.cos(90.0-dec1_rad) * math.cos(90.0-dec2_rad) +
                            math.sin(90.0-dec1_rad) * math.sin(90.0-dec2_rad) *
                            math.cos(ra1_rad - ra2_rad))
        res = math.degrees(sep_rad)
        return res

    deltaStarsRaDecDeg = deltaStarsRaDecDeg1
    
    def get_starsep_RaDecDeg(self, ra1_deg, dec1_deg, ra2_deg, dec2_deg):
        sep = self.deltaStarsRaDecDeg(ra1_deg, dec1_deg, ra2_deg, dec2_deg)
        ## self.logger.debug("sep=%.3f ra1=%f dec1=%f ra2=%f dec2=%f" % (
        ##     sep, ra1_deg, dec1_deg, ra2_deg, dec2_deg))
        sgn, deg, mn, sec = wcs.degToDms(sep)
        if deg != 0:
            txt = '%02d:%02d:%06.3f' % (deg, mn, sec)
        else:
            txt = '%02d:%06.3f' % (mn, sec)
        return txt
        
    def get_starsep_XY(self, x1, y1, x2, y2):
        # source point
        ra_org, dec_org = self.pixtoradec(x1, y1)

        # destination point
        ra_dst, dec_dst = self.pixtoradec(x2, y2)

        return self.get_starsep_RaDecDeg(ra_org, dec_org, ra_dst, dec_dst)

    def get_RaDecOffsets(self, ra1_deg, dec1_deg, ra2_deg, dec2_deg):
        delta_ra_deg = ra1_deg - ra2_deg
        adj = math.cos(math.radians(dec2_deg))
        if delta_ra_deg > 180.0:
            delta_ra_deg = (delta_ra_deg - 360.0) * adj
        elif delta_ra_deg < -180.0:
            delta_ra_deg = (delta_ra_deg + 360.0) * adj
        else:
            delta_ra_deg *= adj

        delta_dec_deg = dec1_deg - dec2_deg
        return (delta_ra_deg, delta_dec_deg)

    # # Is this one more accurate?
    # def get_RaDecOffsets(self, ra1_deg, dec1_deg, ra2_deg, dec2_deg):
    #     sep_ra = self.deltaStarsRaDecDeg(ra1_deg, dec1_deg,
    #                                      ra2_deg, dec1_deg)
    #     if ra1_deg - ra2_deg < 0.0:
    #         sep_ra = -sep_ra

    #     sep_dec = self.deltaStarsRaDecDeg(ra1_deg, dec1_deg,
    #                                       ra1_deg, dec2_deg)
    #     if dec1_deg - dec2_deg < 0.0:
    #         sep_dec = -sep_dec
    #     return (sep_ra, sep_dec)

    def calc_dist_deg2pix(self, ra_deg, dec_deg, delta_deg, equinox=None):
        x1, y1 = self.radectopix(ra_deg, dec_deg, equinox=equinox)

        # add delta in deg to ra and calculate new ra/dec
        ra2_deg = ra_deg + delta_deg
        if ra2_deg > 360.0:
            ra2_deg = math.fmod(ra2_deg, 360.0)
        # then back to new pixel coords
        x2, y2 = self.radectopix(ra2_deg, dec_deg)

        radius_px = abs(x2 - x1)
        return radius_px
        
    def calc_dist_xy(self, x, y, delta_deg):
        # calculate ra/dec of x,y pixel
        ra_deg, dec_deg = self.pixtoradec(x, y)

        # add delta in deg to ra and calculate new ra/dec
        ra2_deg = ra_deg + delta_deg
        if ra2_deg > 360.0:
            ra2_deg = math.fmod(ra2_deg, 360.0)
        # then back to new pixel coords
        x2, y2 = self.radectopix(ra2_deg, dec_deg)
        
        radius_px = abs(x2 - x)
        return radius_px
        
    def calc_dist_center(self, delta_deg):
        return self.calc_dist_xy(self.width // 2, self.height // 2)
        
        
    def calc_compass(self, x, y, len_deg_e, len_deg_n):
        ra_deg, dec_deg = self.pixtoradec(x, y)
        
        ra_e = ra_deg + len_deg_e
        if ra_e > 360.0:
            ra_e = math.fmod(ra_e, 360.0)
        dec_n = dec_deg + len_deg_n

        # Get east and north coordinates
        xe, ye = self.radectopix(ra_e, dec_deg)
        xe = int(round(xe))
        ye = int(round(ye))
        xn, yn = self.radectopix(ra_deg, dec_n)
        xn = int(round(xn))
        yn = int(round(yn))
        
        return (x, y, xn, yn, xe, ye)
       
    def calc_compass_center(self):
        # calculate center of data
        x = self.width // 2
        y = self.height // 2

        # calculate ra/dec at 1 deg East and 1 deg North
        ra_deg, dec_deg = self.pixtoradec(x, y)
        # TODO: need to correct for ra_deg+1 >= 360?  How about dec correction
        xe, ye = self.radectopix(ra_deg+1.0, dec_deg)
        xn, yn = self.radectopix(ra_deg, dec_deg+1.0)

        # now calculate the length in pixels of those arcs
        # (planar geometry is good enough here)
        px_per_deg_e = math.sqrt(math.fabs(ye - y)**2 + math.fabs(xe - x)**2)
        px_per_deg_n = math.sqrt(math.fabs(yn - y)**2 + math.fabs(xn - x)**2)

        # radius we want the arms to be (approx 1/4 the smallest dimension)
        radius_px = float(min(self.width, self.height)) / 4.0

        # now calculate the arm length in degrees for each arm
        # (this produces same-length arms)
        len_deg_e = radius_px / px_per_deg_e
        len_deg_n = radius_px / px_per_deg_n

        return self.calc_compass(x, y, len_deg_e, len_deg_n)

    
#END
