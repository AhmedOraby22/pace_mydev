#!/usr/bin/python3
"""diskguard: refuse to give a disk that belongs to ANOTHER pool to an automatic replace/attach (test 674 step 6).

While its owner node was down, the test pool P1 was not imported on the surviving node and its disks looked free there:
selectspare ran `zpool replace -f pdhcp588910935 dm-1 <P1 disk>` (the -f also overrides ZFS's own "is part of exported
pool" refusal), so one disk ended up in two pools and both were damaged.  A disk whose ZFS label names a pool other than
the one being healed is not a spare.
"""
import subprocess

def labelpools(disk):
    """The pool names in the ZFS labels of disk (by-id name, /dev path or dm name): whole disk and its first partition."""
    base = disk if disk.startswith('/dev/') else '/dev/disk/by-id/'+disk
    if not disk.startswith('/dev/') and (disk.startswith('dm-') or disk.startswith('sd')):
        base = '/dev/'+disk
    names = set()
    for dev in (base, base+'-part1', base+'1'):
        try:
            out = subprocess.run(['/sbin/zdb', '-l', dev], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20).stdout.decode('utf-8', 'replace')
        except Exception:
            continue
        for line in out.split('\n'):
            line = line.strip()
            if line.startswith('name:'):
                names.add(line.split(':', 1)[1].strip().strip("'"))
    return names

def foreignpool(disk, poolname):
    """The name of another pool that disk belongs to, or '' when it is free or already this pool's."""
    others = sorted(n for n in labelpools(disk) if n and n != poolname)
    return others[0] if others else ''
