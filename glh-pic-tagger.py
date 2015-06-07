#!/usr/bin/env python
import bisect
import collections
import dateutil
from dateutil import parser
import glob
import optparse
import piexif
import xml.etree.ElementTree as ET

KMLNS = {'gx': 'http://www.google.com/kml/ext/2.2'}

GPSInfo = collections.namedtuple(
    'GPSInfo', ['latitude', 'longitude', 'altitude'])

def kml_loc_to_gpsinfo(loc):
    longitude, latitude, altitude = (
            loc.strip().split(' '))
    return GPSInfo(float(latitude), float(longitude), float(altitude))

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
    opt_parser.add_option(
            '-l', '--locaction', dest='loc',
            help='Location to set')

    options, args = opt_parser.parse_args()

    if options.loc:
        parts = options.loc.split(',')
        if len(parts) < 2 or len(parts) > 3:
            print 'location must be 2 or 3 parts'
            return
        specified_gps_info = GPSInfo(
                float(parts[0].strip()), float(parts[1].strip()),
                float(parts[2].strip()) if len(parts) == 3 else None)
    else:
        specified_gps_info = None

    if not specified_gps_info:
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
            try:
                exif = piexif.load(fn)
            except:
                print 'Fail to load exif from %s' % fn
                continue
            if specified_gps_info:
                gps_info = specified_gps_info
            else:
                time = exif['Exif'][piexif.ExifIFD.DateTimeOriginal]
                if not time:
                    print 'DateTimeOriginal not found in ' + fn
                    continue
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

                gps_info = kml_loc_to_gpsinfo(timed_locs[g][1])

            lonref, lon = to_gps_latlon(gps_info.longitude, ('E', 'W'))
            exif['GPS'][piexif.GPSIFD.GPSLongitudeRef] = lonref
            exif['GPS'][piexif.GPSIFD.GPSLongitude] = lon

            latref, lat = to_gps_latlon(gps_info.latitude, ('N', 'S'))
            exif['GPS'][piexif.GPSIFD.GPSLatitudeRef] = latref
            exif['GPS'][piexif.GPSIFD.GPSLatitude] = lat

            if gps_info.altitude:
                altref, alt = to_gps_alt(gps_info.altitude)
                exif['GPS'][piexif.GPSIFD.GPSAltitudeRef] = altref
                exif['GPS'][piexif.GPSIFD.GPSAltitude] = alt

            if not specified_gps_info:
                u = timed_locs[g][0].utctimetuple()
                exif['GPS'][piexif.GPSIFD.GPSTimeStamp] = (
                        (u.tm_hour, 0), (u.tm_min, 0), (u.tm_sec, 0))
                exif['GPS'][piexif.GPSIFD.GPSDateStamp] = '%04d:%02d:%02d' % (
                        u.tm_year, u.tm_mon, u.tm_mday)

            piexif.insert(piexif.dump(exif), fn)

            if specified_gps_info:
                print 'Tagged %s' % fn
            else:
                dt = timed_locs[g][0] - t
                print 'Tagged %s (%s) with %d seconds certainty at %s, %s' % (
                        fn, time, abs(dt.total_seconds()), gps_info.latitude,
                                      gps_info.longitude)

if __name__ == '__main__':
    main()

