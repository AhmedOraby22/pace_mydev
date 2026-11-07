#!/usr/bin/python3
import subprocess,sys,datetime
from etcdgetpy import etcdget as get
from etcdgetnoportpy import etcdget as getnoport
from etcdput import etcdput as put
from etcddel import etcddel as dels 
from ast import literal_eval as mtuple
from time import time as _timestamp

leader, leaderip, myhost, myhostip = '','','',''
def usrfninit(ldr,ldrip,hst,hstip,pprt='-1'):
 global allusers, leader ,leaderip, myhost, myhostip, pport
 leader, leaderip, myhost, myhostip, pport = ldr, ldrip, hst, hstip, pprt
 return
allusers = []

def thread_add(user,syncip, tosync='pullavail'):
 global myusers
 global allusers, leader ,leaderip, myhost, myhostip,pport
 username=user[0].replace('usersinfo/','')
 if 'NoUser' == username:
  return
 with open('/root/usersync2','w') as f:
  f.write(str(user)+' + '+str(username)+'\n')
 
 # test 619 step 1: a copy whose read from the leader failed (the cluster link was down for seconds) was not made and nothing
 # said so; the node reported in sync without the user. A failed read or a failed UnixAddUser is logged and returns False:
 # oneusersync hands it to checksyncs, which keeps the sync request for its next pass.
 try:
  if 'pullsync' in tosync:
    userhash=getnoport(leaderip,pport,'usershash/'+username)[0]
    everyone=getnoport(leaderip,pport,'usersigroup/Everyone',username)
    if '_1' not in str(everyone):
        everyone=',Everyone'
    else:
        everyone=''
  else:
    userhash=get(leaderip,'usershash/'+username)[0]
    everyone=get(leaderip, 'usersigroup/Everyone',username)
    if '_1' not in str(everyone):
        everyone=',Everyone'
    else:
        everyone=''
 except Exception as e:
  synclog(username, 'cannot read it from the leader: '+str(e))
  return False
 if str(userhash).strip() in ('', '_1', '-1', 'None'):
  synclog(username, 'no usershash on the leader (read failed or not written yet)')
  return False
 userinfo=user[1].split(':')
 userid=userinfo[0]
 usergd=userinfo[1]
 usersplit = user[1].split('/')
 homePool = usersplit[1]
 usergroups = usersplit[2] 
 userpass = userhash
 size = usersplit[3]
 HomeAddr = usersplit[-3]
 HomeSubnet = usersplit[-2]
 active = usersplit[-1]
 permissions = ",".join(usersplit[4:-3])
 cmdline=['/TopStor/UnixAddUser',leaderip,username, homePool, 'groups'+usergroups+everyone,userhash, size, HomeAddr, HomeSubnet, tosync, userid,usergd,active, permissions,'system']
 print('***************************')
 print(cmdline)
 print('***************************')
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)
 if result.returncode != 0:
  synclog(username, 'UnixAddUser exit '+str(result.returncode))
  return False
 return True

def synclog(username, why):
 print('user sync copy failed', username, why)
 try:
  with open('/root/usersyncfail.log','a') as f:
   f.write(str(datetime.datetime.now())+' sync copy of user '+username+' failed: '+why+'\n')
 except Exception:
  pass

def thread_del(username,syncip, pullsync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip
 global allusers
 if  'NoUser' == username:
  return
 # exact names (test 614): 'q015a' in str(allusers) was true while only q015a1 / xq015a were left, and
 # dels(syncip,'user','q015a') deleted every user* key whose key or value contains the text (usersinfo/q015a1,
 # usershash/q015a10, usersigroup/q015ag, usersigroup/Everyone) from this node's etcd
 if 'usersinfo/'+username not in [ str(u[0]) for u in allusers if isinstance(u,(tuple,list)) ] and 'admin' != username:
  cmdline=['/TopStor/UnixDelUser',leaderip, username,'system',pullsync]
  result=subprocess.run(cmdline,stdout=subprocess.PIPE)
  dels(syncip,'usersinfo/'+username)
  dels(syncip,'usershash/'+username)

def usersyncall(tosync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip,pport
 global allusers
 global myusers
 if 'pullsync' in tosync:
    allusers=getnoport(leaderip,pport,'usersinfo','--prefix')
 else:
    allusers=get(leaderip,'usersinfo','--prefix')
 if myhost in leader:
    syncip = leaderip
 else:
    syncip = myhostip
 myusers=get(syncip,'usersinfo','--prefix')
 threads=[]
 if '_1' in allusers:
  allusers=[]
 if '_1' in myusers:
  myusers=[]
 for user in allusers:
  thread_add(user,syncip, tosync)
 if 'pullsync' in tosync:
  pulladminhash('admin')
 elif myhost not in str(leader):
  # admin has no usersinfo, so no UnixAddUser above carries its hash: a node that was down while the admin
  # password changed kept the old one in its etcd and handed it to the cluster when it became the leader
  try:
   newhash = str(get(leaderip,'usershash/admin')[0]).replace('\n','')
   if newhash not in ('_1','-1','','None') and len(newhash) > 3 and newhash != str(get(myhostip,'usershash/admin')[0]).replace('\n',''):
    put(myhostip,'usershash/admin',newhash)
    subprocess.run(['/TopStor/UnixChangePass','admin','admin'],stdout=subprocess.PIPE)
  except Exception as e:
   print('admin hash sync', e)
 leader=get(leaderip,'leader','--prefix')
 if myhost not in str(leader) or 'pullsync' in tosync:
  for user in myusers:
   if user not in allusers:
     user=user[0].replace('usersinfo/','')
     thread_del(user, syncip, tosync)

def pulladminhash(username='admin'):
 """Receiver (DR site) side of the replication: the password hash of `username` on the sending cluster replaces the one
 on this cluster, so the sender's admin password also logs in here (QualityCheck replication tests).  The hash is
 encrypted with a key that depends only on the user name, so it is valid on any cluster.  The new hash is stored in
 this cluster's leader etcd and a 'passwd' sync request makes every node apply it (UnixChangePass reads it from etcd).
 Only for admin and for users that already exist here (their own usersinfo), never creates a stray usershash key."""
 global leaderip, pport
 try:
  newhash = str(getnoport(leaderip, pport, 'usershash/'+username)[0]).replace('\n','')
  oldhash = str(get(leaderip, 'usershash/'+username)[0]).replace('\n','')
  if username != 'admin' and str(get(leaderip, 'usersinfo/'+username)[0]) in ('_1', '-1', '', 'None'):
   return False
 except Exception as e:
  print('pulladminhash: cannot read the hash of', username, e)
  return False
 if len(newhash) < 3 or newhash == '_1' or newhash == oldhash:
  return False
 print('pulladminhash: the password of', username, 'follows the sending cluster')
 put(leaderip, 'usershash/'+username, newhash)
 dels(leaderip, 'sync', 'UnixChangePass_'+username+'_')
 put(leaderip, 'sync/passwd/UnixChangePass_'+username+'_admin/request', 'passwd_'+str(int(_timestamp()*1000)))
 return True

def oneusersync(oper,usertosync,tosync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip, pport
 print('args',oper,usertosync)
 if myhost in leader:
    syncip = leaderip
 else:
    syncip = myhostip
 
 if oper == 'Add':
    # the user with EXACTLY this name (a filter argument matches any text of a key/value pair: adding q015a
    # could take usersinfo/aq015a, whatever comes first)
    if 'pullsync' in tosync:
        users=getnoport(leaderip,pport,'usersinfo/'+usertosync, '--prefix')
    else:
        users=get(leaderip,'usersinfo/'+usertosync, '--prefix')
    user=[ u for u in users if isinstance(u,(tuple,list)) and u[0] == 'usersinfo/'+usertosync ]
    if len(user) == 0:
        print('oneusersync: no user',usertosync,'on the leader')
        return
    return thread_add(user[0],syncip,tosync)
 else:
    user = usertosync
    # the users of the leader NOW (allusers was the list of the last full sync of this long running process: it still
    # held the user being deleted, so the delete was skipped on this node)
    try:
     if 'pullsync' in tosync:
        allusers=getnoport(leaderip,pport,'usersinfo','--prefix')
     else:
        allusers=get(leaderip,'usersinfo','--prefix')
    except Exception as e:
     print('oneusersync: cannot read the users of the leader', e)
    thread_del(user,syncip,tosync)
 
  
if __name__=='__main__':
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leader'
 leader=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leaderip'
 leaderip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternode'
 myhost=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip'
 myhostip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 if len(sys.argv[1:]) < 2:
    usersyncall(*sys.argv[1:])
 else:
    oneusersync(*sys.argv[1:])
