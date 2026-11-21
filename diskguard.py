#!/usr/bin/python3
"""diskguard: refuse to give a disk that belongs to ANOTHER pool to an automatic replace/attach (test 674 step 6).

While its owner node was down, the test pool P1 was not imported on the surviving node and its disks looked free there:
selectspare ran `zpool replace -f pdhcp588910935 dm-1 <P1 disk>` (the -f also overrides ZFS's own "is part of exported
pool" refusal), so one disk ended up in two pools and both were damaged.  A disk whose ZFS label names a pool other than
the one being healed is not a spare.
"""
import subprocess

def labelinfo(disk):
    """(pool name, pool_guid) pairs from the ZFS labels of disk: whole disk and its first partition."""
    base = disk if disk.startswith('/dev/') else '/dev/disk/by-id/'+disk
    if not disk.startswith('/dev/') and (disk.startswith('dm-') or disk.startswith('sd')):
        base = '/dev/'+disk
    pairs = set()
    for dev in (base, base+'-part1', base+'1'):
        try:
            out = subprocess.run(['/sbin/zdb', '-l', dev], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20).stdout.decode('utf-8', 'replace')
        except Exception:
            continue
        name = guid = ''
        for line in out.split(chr(10)):
            line = line.strip()
            if line.startswith('name:') and not name:
                name = line.split(':', 1)[1].strip().strip("'")
            elif line.startswith('pool_guid:') and not guid:
                guid = line.split(':', 1)[1].strip()
        if name:
            pairs.add((name, guid))
    return pairs

def liveguids():
    """pool guids that are alive: imported on this node, or recorded as ActPool/<pool> in the cluster etcd"""
    guids = set()
    try:
        out = subprocess.run(['/sbin/zpool', 'get', '-H', '-o', 'value', 'guid'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20).stdout.decode()
        guids.update(x.strip() for x in out.split() if x.strip())
    except Exception:
        pass
    try:
        from etcdgetlocalpy import etcdget as getlocal
        from etcdgetpy import etcdget as get
        leaderip = str(getlocal('leaderip')[0])
        for k in get(leaderip, 'ActPool', '--prefix'):
            if isinstance(k, (tuple, list)) and len(k) > 1:
                guids.add(str(k[1]).strip())
    except Exception:
        pass
    return guids

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
    """The name of another LIVE pool that disk belongs to, or '' when it is free, already this pool's, or only carries a dead
    label (test 680: a stale label of an old copy of pdhcp588910935, other pool_guid, blocked every replace and the pool
    stayed degraded).  A label counts when its pool_guid is imported here or recorded in ActPool/ of the cluster."""
    pairs = [ (n, g) for n, g in labelinfo(disk) if n and n != poolname ]
    if not pairs:
        return ''
    live = liveguids()
    others = sorted(n for n, g in pairs if not g or g in live)
    return others[0] if others else ''
