#!/usr/bin/python3
import subprocess,sys, os, fcntl
from etcdgetpy import etcdget as get
from etcdput import etcdput as put 
from etcddel import etcddel as dels 
#from broadcasttolocal import broadcasttolocal 
from time import time as stamp
from glob import glob


#leader=get('leader','--prefix')[0][0].split('/')[1]

def dosync(*args):
  global leaderip, leader
  put(leaderip, *args)
  put(leaderip, args[0]+'/'+leader,args[1])
  return 

def getippos(vtype):
    print('vtype',vtype)
    if vtype in ['cifs', 'home']:
        return 7
    elif 'nfs' in vtype:
        return 9
    else: 
        return 0
def getdirtyvols(vtype, etcds, replis, dockers):
    global leader, leaderip, myhost, myhostip, etcdip
    cmdline = '/TopStor/getvols.sh '+vtype
    result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split('\n')
    result = [x for x in result if 'pdhc' in x]
    resultdisabled = [ x for x in result if 'disable' in str(x) ]
    resultactive = [ x for x in result if 'active' in str(x) ]
    etcddisabled= [ x for x in etcds if 'disable' in str(x) ]
    etcdactive= [ x for x in etcds if 'active' in str(x) ]
    dirtyset = set()
    ipset = set()
    for res in result:
        reslist=res.split('/')
        ippos = getippos(vtype)
        if reslist[-1] == 'active':
            if reslist[1] in str(etcddisabled):
                dirtyset.add(res)
        else:
            if reslist[1] in str(etcdactive):
                dirtyset.add(res)
                print('here2', res)
        if reslist[1] not in str(etcds):
            dirtyset.add(res)
        for dckr in dockers.split('\n'):
            dckrip = dckr.split(' ')[-1].split('-')[-1]
            if dckrip != reslist[ippos]:
                continue
            if reslist[ippos] in dckr and reslist[-1] =='active':
                dckrname=dckr.split(' ')[-1]
                cmdline = 'docker inspect '+dckrname
                result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
                print(dckrname, reslist[1],reslist)
                if reslist[1] not in str(result):
                    print('gggggggggggggggggggggggggggggggggggggggggg')
                    print('not in',ippos, reslist[ippos], dckrip)
                    print('reslist1',reslist[1], dckrname)
                    print('gggggggggggggggggggggggggggggggggggggggggg')
                    dirtyset.add(res)
        if reslist[ippos] not in dockers and 'active' in reslist[-1]:
            dirtyset.add(res)
    print('dirtyset', dirtyset)
    return dirtyset

def nfs( etcds, replis, exports):
    global leader, leaderip, myhost, myhostip, etcdip
    #dirtyset = getdirtyvols('nfs', etcds, replis, )
    flag = 0
    for export in exports:
        with open(export) as f:
            pool = export.split('/')[1]
            vol = export.split('.')[1]
            print(pool,vol)
            exportetctip = 0
            for line in f:
                if len(line) < 5:
                    continue
                print('theline',line)
                if 'SUMMARY' in line:
                    exportetc = line.split(' ')[3]
                    exportetcip = exportetc.split('/')[-3]
                    exportetcsub = exportetc.split('/')[-2]
                    exportetcactive = exportetc.split('/')[-1]
                    if exportetc[2:-2] not in str(etcds):
                        dels(leaderip, 'volumes', vol)
                        put(leaderip,'volumes/NFS/'+myhost+'/'+pool+'/'+vol,exportetc)
                        flag = 1
                else:
                    if 'active' in exportetcactive: 
                        with open('/TopStordata/exportip.'+vol+'_'+exportetcip, 'w') as fip:
                            fip.write(line)
                        cmdline = '/TopStor/nfs.sh '+exportetcip+' '+exportetcsub
                        subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
                    else:
                        cmdline = '/TopStor/nfsumount.sh '+vol
                        subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
    if flag:
        dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
        
    return    

def nfsnew( etcds, replis, dockers):
 global leader, leaderip, myhost, myhostip, etcdip
 dirtyset = getdirtyvols('nfs', etcds, replis, dockers)
 print('cccccccccccccccccccccccccccccc')
 print('dirty',dirtyset)
 print('cccccccccccccccccccccccccccccc')
 # QSD5.337 (test 646 QX-047 step 3): VolumeChangeNFS rebuilds the container of a changed address itself and holds the address
 # lock (/tmp/shareaddr.<ip>.lock) meanwhile; this pass rebuilt the same container in parallel. A locked address is skipped
 # (the next pass looks again); the lock is held here while the container is rebuilt (nfsnew.sh does not lock again,
 # SHAREADDR_LOCK); a container that is running with the volume once the lock is ours (rebuilt by the holder) is left alone.
 for res in dirtyset:
   reslist=res.split('/')
   ipaddr = reslist[getippos('nfs')]
   print('update',reslist[1])
   lockf = addrlock(ipaddr)
   if lockf is None:
     print('address',ipaddr,'is being changed by another job, skipped')
     continue
   try:
     left='volumes/NFS/'+myhost+'/'+'/'.join(reslist[0:2])
     if reslist[-1] == 'active' and inrunning('NFS-'+ipaddr, '"/'+reslist[0]+'/'+reslist[1]+'"'):
       put(leaderip, left,res)
       dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
       print('container NFS-'+ipaddr+' already runs with',reslist[1])
       continue
     cmdline = '/TopStor/undockerthis.sh '+ipaddr
     result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
     put(leaderip, left,res)
     dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
     cmdline='/TopStor/nfsnew.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[9]+' '+reslist[10]+' NFS'
     print('aloooooooooooooooooooooo')
     print(cmdline)
     result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE, env=dict(os.environ, SHAREADDR_LOCK=ipaddr)).stdout.decode('utf-8')
     put(etcdip,'dirty/volume','0')
   finally:
     lockf.close()

def addrlock(ipaddr):
 # the per-address lock of shareaddr changes (VolumeChangeNFS, nfsnew.sh); None when another job holds it
 try:
   lockf = open('/tmp/shareaddr.'+ipaddr+'.lock', 'w')
 except OSError:
   return open(os.devnull, 'w')   # no lock file possible: work as before, without the lock
 try:
   fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
 except OSError:
   lockf.close()
   return None
 return lockf

def inrunning(dckrname, mountsrc):
 cmdline = 'docker ps --format {{.Names}}'
 names = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split()
 if dckrname not in names:
   return False
 cmdline = 'docker inspect '+dckrname
 return mountsrc in subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')

def repairbyaddress(dirtyset, leftof, cmdof):
 # test 643 step 3: every share of an address runs in one container. A missing container made all its shares dirty and
 # each one removed and re-created that same container (N shares, N restarts ~14 s apart). The shares are repaired per
 # address: the container is removed and started once (cifs.py starts it with every share of the address).
 global leader, leaderip, myhost, myhostip, etcdip
 byaddress = dict()
 for res in sorted(dirtyset):
   byaddress.setdefault(res.split('/')[7], []).append(res)
 for ipaddr in byaddress:
   ress = byaddress[ipaddr]
   print('update',ipaddr,[ x.split('/')[1] for x in ress ])
   cmdline = '/TopStor/undockerthis.sh '+ipaddr
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   for res in ress:
     left = leftof(res.split('/'))
     put(leaderip, left,res)
     print('tosync this',leaderip, left,res)
   dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
   cmdline = cmdof(ress[0].split('/'))
   print('cifs.py: '+cmdline)
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
   print('cifs result',result)
   put(etcdip,'dirty/volume','0')
 return len(byaddress) > 0

def cifs( etcds, replis, dockers):
 global leader, leaderip, myhost, myhostip, etcdip
 dirtyset = getdirtyvols('cifs', etcds, replis, dockers)
 print('cccccccccccccccccccccccccccccc')
 print('dirty',dirtyset)
 print('cccccccccccccccccccccccccccccc')
 def leftof(reslist):
   if 'DOMAIN' in str(reslist):
    return 'volumes/CIFS_'+reslist[9]+'/'+myhost+'/'+'/'.join(reslist[0:2])
   return 'volumes/CIFS/'+myhost+'/'+'/'.join(reslist[0:2])
 def cmdof(reslist):
   if 'DOMAIN' in str(reslist):
     return '/TopStor/cifs.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[7]+' '+reslist[8]+' CIFS_'+reslist[9]+' '+' '.join(reslist[9:])
   return '/TopStor/cifs.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[7]+' '+reslist[8]+' CIFS '+' '.join(reslist[9:])
 return repairbyaddress(dirtyset, leftof, cmdof)

def homes(etcds, replis, dockers):
 global leader, leaderip, myhost, myhostip, etcdip
 print('----------------')
 dirtyset = getdirtyvols('home', etcds, replis, dockers)
 print('hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh')
 print('dirty',dirtyset)
 print('hhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhhh')
 def leftof(reslist):
   return 'volumes/HOMEE/'+myhost+'/'+'/'.join(reslist[0:2])
 def cmdof(reslist):
   return '/TopStor/cifs.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[7]+' '+reslist[8]+' HOMEE '+' '.join(reslist[9:])
 return repairbyaddress(dirtyset, leftof, cmdof)


def iscsi(etcds, replis):
 global leader, leaderip, myhost, myhostip, etcdip
 cmdline = 'targetcli ls '
 targets = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8') 
 cmdline = '/TopStor/getvols.sh iscsi'
 result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split('\n')
 result = [x for x in result if 'pdhc' in x]
 for res in result:
  reslist=res.split('/')
  print('reslist1',reslist[1])
  if reslist[1] not in str(etcds):
   left='volumes/ISCSI/'+myhost+'/'+'/'.join(reslist[0:2])
   put(leaderip, left,res)
   dosync('sync/volumes/_'+myhost+'/request','volumes_'+str(stamp()))
   #broadcasttolocal(left,res)
  if reslist[1] not in targets:
   print(reslist)
   cmdline='/TopStor/iscsi.py '+leader+' '+leaderip+' '+myhost+' '+myhostip+' '+etcdip+' '+reslist[0]+' '+reslist[1]+' '+reslist[2]+' '+reslist[3]+' ISCSI '+reslist[4]+' '+reslist[5]+' '+reslist[6]+' '+reslist[7]
   result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')

def cleanfailed(dockers):
    fails = ['timeerror','ADnameerror', 'ADservererror']
    doms = [ (doc.split('-')[-1],doc.split(' ')[0]) for doc in dockers.split('\n') if 'CIFS_' in str(doc)]
    for dom in doms:
        cmdline = '/TopStor/getdomvolstatus.sh '+dom[0]
        result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').split('_result')[1]
        print('dock:',cmdline,'....',result)
        if result in fails:
            print('cleaning',dom[0],dom[1])
            cmdline = 'docker rm -f '+ dom[1]
            result = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8')
    
def volumecheck(etcds, replis, *args):
 global leader, leaderip, myhost, myhostip, etcdip
 if str(etcds)=='init':
     leader = replis 
     leaderip = args[0]
     myhost = args[1]
     myhostip = args[2]
     etcdip = args[3]
     return

 cmdline = 'docker ps'
 dockers = subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8') 
 #cmdline = 'ls /TopStordata'
 #exports = subprocess.run(cmdline.split(),shell=True, stdout=subprocess.PIPE).stdout.decode('utf-8')
 #cmdline = 'rm -rf /TopStordata/exportip*'
 #subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8') 
 #exports = glob('/pdhc*/exports*')
 with open('/root/volumecheck','w') as f:
  f.write(str(etcds))
 #exports = [ x.split('exports.')[1] for x in exports ]
 print('----------------------------------------------------')
 print(etcds,'\n',dockers)
 nfsnew(etcds, replis, dockers)
 print('----------------------------------------------------')
 if cifs(etcds, replis, dockers):
     # containers were re-created: the later checks look at the containers as they are now
     dockers = subprocess.run(['docker','ps'],stdout=subprocess.PIPE).stdout.decode('utf-8')
 #nfs(etcds, replis, exports)
 if homes(etcds, replis, dockers):
     dockers = subprocess.run(['docker','ps'],stdout=subprocess.PIPE).stdout.decode('utf-8')
 iscsi(etcds, replis)
 cleanfailed(dockers) 
   
if __name__=='__main__':
  leaderip = sys.argv[1]
  myhost = sys.argv[2]
  leader=get(leaderip, 'leader')[0]
  myhostip=get(leaderip,'ready/'+myhost)[0] 
  if myhost == leader:
   etcdip = leaderip
  else:
   etcdip = myhostip
   
 
  etcds = get(etcdip, 'volumes','--prefix')
  replis = get(etcdip, 'replivol','--prefix')
  volumecheck(etcds, replis)
