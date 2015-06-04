#!/usr/bin/env python
import bisect
import dateutil
from dateutil import parser
import glob
import optparse
import piexif
import xml.etree.ElementTree as ET

KMLNS = {'gx': 'http://www.google.com/kml/ext/2.2'}

def to_gps_latlon(v, refs):
    ref = refs[0] if v >= 0 else refs[1]
    dd = abs(v)
    d = int(dd)
    mm = (dd - d) * 60
    m = int(mm)
    ss = (mm - m) * 60
    s = int(ss * 100)
    r = ((d, 1), (m, 1), (s, 100))
    return (ref, r)

def to_gps_alt(v):
    ref = 0 if v >= 0 else 1
    return (ref, (abs(int(v)), 1))

def main():
    opt_parser = optparse.OptionParser()
    options, args = opt_parser.parse_args()
    time_maps = {}

    for fn in args:
        if fn.endswith('.kml'):
            kml = ET.parse(fn)
            track = kml.find('.//gx:Track', KMLNS)
            when = coord = None
            for e in track.getchildren():
                if e.tag.endswith('when'):
                    when = parser.parse(e.text)
                elif e.tag.endswith('coord'):
                    coord = e.text
                    time_maps[when] = coord

    timed_locs = sorted(time_maps.iteritems())
    default_tz = None
    tzs = set(x.tzinfo.utcoffset(None) for x, _ in timed_locs)
    if len(tzs) == 1:
        default_tz = timed_locs[0][0].tzinfo

    for fn in args:
        if not fn.endswith('.kml'):
            exif = piexif.load(fn)
            time = exif['Exif'][piexif.ExifIFD.DateTimeOriginal]
            if time:
                dp, tp = time.split(' ', 2)
                time = ' '.join([dp.replace(':', '/'), tp]);
                t = parser.parse(time)
                if not t.tzinfo:
                    t = t.replace(tzinfo=default_tz)

                p = bisect.bisect(timed_locs, (t, None))
                if p == 0:
                    g = 0
                elif p == len(timed_locs):
                    g = len(timed_locs) - 1
                else:
                    dt0 = t - timed_locs[p - 1][0]
                    dt1 = timed_locs[p][0] - t
                    if dt0 < dt1:
                        g = p - 1
                    else:
                        g = p

                longitude, latitude, altitude = (
                        timed_locs[g][1].strip().split(' '))

                lonref, lon = to_gps_latlon(float(longitude), ('E', 'W'))
                exif['GPS'][piexif.GPSIFD.GPSLongitudeRef] = lonref
                exif['GPS'][piexif.GPSIFD.GPSLongitude] = lon

                latref, lat = to_gps_latlon(float(latitude), ('N', 'S'))
                exif['GPS'][piexif.GPSIFD.GPSLatitudeRef] = latref
                exif['GPS'][piexif.GPSIFD.GPSLatitude] = lat

                altref, alt = to_gps_alt(float(altitude))
                exif['GPS'][piexif.GPSIFD.GPSAltitudeRef] = altref
                exif['GPS'][piexif.GPSIFD.GPSAltitude] = alt

                u = timed_locs[g][0].utctimetuple()
                exif['GPS'][piexif.GPSIFD.GPSTimeStamp] = (
                        (u.tm_hour, 0), (u.tm_min, 0), (u.tm_sec, 0))
                exif['GPS'][piexif.GPSIFD.GPSDateStamp] = '%04d:%02d:%02d' % (
                        u.tm_year, u.tm_mon, u.tm_mday)

                piexif.insert(piexif.dump(exif), fn)
                dt = timed_locs[g][0] - t
                print 'Tagged %s (%s) with %d seconds certainty at %s, %s' % (
                        fn, time, abs(dt.total_seconds()), latitude, longitude)
            else:
                print 'DateTimeOriginal not found in ' + fn

if __name__ == '__main__':
    main()

