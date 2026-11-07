#!/usr/bin/python3
import subprocess,sys,re
from etcdgetpy import etcdget as get
from etcdgetnoportpy import etcdget as getnoport
from etcdput import etcdput as put
from etcddel import etcddel as dels 
from ast import literal_eval as mtuple
from socket import gethostname as hostname

allusers= []
leader, leaderip, myhost, myhostip = '','','',''


def grpfninit(ldr,ldrip,hst,hstip,pprt='-1'):
 global allusers, leader ,leaderip, myhost, myhostip,pport
 leader, leaderip, myhost, myhostip, pport = ldr, ldrip, hst, hstip, pprt
 return
#def thread_add(*user):

def thread_add(user,syncip,pullsync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip
 username=user[0].replace('usersigroup/','')
 if 'Everyone' == username:
  # Everyone is made on every node by its setup and never changed by a sync, but its row (all users) is copied: a follower
  # without it read _1 and wrote _1/<user>/_1 when it added a user to it (test 620)
  everyonecopy(user,syncip)
  return
 groupusers=user[1].split('/')[2]
 if groupusers=='no':
  groupusers='users'
 else:
  groupusers='users'+groupusers
 try:
  userigroup=user[1].split(':')
  userid=userigroup[0]
  usergd=userigroup[1]
 except:
    return
 cmdline=['/TopStor/UnixAddGroup',leaderip, username, groupusers, pullsync, userid,usergd, 'system']
 put(syncip, user[0],user[1])
 result=subprocess.run(cmdline,stdout=subprocess.PIPE)

def everyonecopy(row,syncip):
 # the leader's usersigroup/Everyone row, exactly, into this node's etcd (only a real value: never _1 or a garbled one);
 # only on a follower of this cluster (a replication receiver keeps its own Everyone)
 global leader, myhost
 try:
  if myhost not in leader and row[0] == 'usersigroup/Everyone' and re.match(r'[0-9]+:[0-9]+:[^/]*/[^/]*/[^/]*/', str(row[1])) and str(row[1]) != str(get(syncip,'usersigroup/Everyone')[0]):
   put(syncip, row[0], row[1])
 except Exception as e:
  print('everyonecopy', e)

#def thread_del(*user):
def thread_del(username,pullsync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip
 if 'Everyone' == username:
  return
 print(username)
 # exact group names (test 614): 'q015ag' in str(allusers) was also true for a member or a group named q015ag2
 if 'usersigroup/'+username not in [ str(g[0]) for g in allusers if isinstance(g,(tuple,list)) ]:
  print(username,str(allusers))
  cmdline=['/TopStor/UnixDelGroup',leaderip, username,'system',pullsync]
  result=subprocess.run(cmdline,stdout=subprocess.PIPE)

def groupsyncall(tosync=''):
 global allusers, leader ,leaderip, myhost, myhostip, pport
 global myusers
 if 'pullsync' in tosync:
    allusers=getnoport(leaderip,pport,'usersigroup','--prefix')
 else:
    allusers=get(leaderip,'usersigroup','--prefix')
 if myhost in leader:
    syncip = leaderip
 else:
    syncip = myhostip
 myusers=get(syncip,'usersigroup','--prefix')
 print(';;;;;',myusers,allusers)
 threads=[]
 if '_1' in allusers:
  allusers=[]
 if '_1' in myusers:
  myusers=[]
 for user in myusers:
  if user not in allusers:
   user = user[0].split('/')[1] 
   thread_del(user)
   dels(syncip, user[0])

 for user in allusers:
  print(user)
  thread_add(user,syncip)
  put(syncip, user[0],user[1])
   
def onegroupsync(oper,usertosync,tosync='pullavail'):
 global allusers, leader ,leaderip, myhost, myhostip, pport
 if myhost in leader:
    syncip = leaderip
 else:
    syncip = myhostip
 if oper == 'Add':
    # the group with EXACTLY this name: get(leaderip,'usersigroup',name)[0] was the first key/value pair whose text
    # contains the name (usersigroup/Everyone holds every user name; q015a also matched q015ag), so a wrong group was made
    if 'pullsync' in tosync:
        groups=getnoport(leaderip, pport, 'usersigroup/'+usertosync, '--prefix')
    else:
        groups=get(leaderip,'usersigroup/'+usertosync, '--prefix')
    user=[ g for g in groups if isinstance(g,(tuple,list)) and g[0] == 'usersigroup/'+usertosync ]
    if len(user) == 0:
        print('onegroupsync: no group',usertosync,'on the leader')
        return
    thread_add(user[0],syncip)
    # and the Everyone row of the leader (a garbled local copy is repaired with the next group sync)
    try:
     everyone=[]
     if 'pullsync' not in tosync and myhost not in leader:
        everyone=get(leaderip, 'usersigroup/Everyone', '--prefix')
     for row in [ g for g in everyone if isinstance(g,(tuple,list)) and g[0] == 'usersigroup/Everyone' ]:
        everyonecopy(row,syncip)
    except Exception as e:
     print('onegroupsync: no Everyone row of the leader', e)
 else:
    user = usertosync
    # the groups of the leader NOW (allusers of the last full sync may still hold the deleted group)
    try:
     if 'pullsync' in tosync:
        allusers=getnoport(leaderip,pport,'usersigroup','--prefix')
     else:
        allusers=get(leaderip,'usersigroup','--prefix')
    except Exception as e:
     print('onegroupsync: cannot read the groups of the leader', e)
    thread_del(user,tosync)
    
 
  
if __name__=='__main__':
 with open('/root/sync2','w') as f:
  f.write('Starting\n')

 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leader'
 leader=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py leaderip'
 leaderip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternode'
 myhost=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 cmdline='docker exec etcdclient /TopStor/etcdgetlocal.py clusternodeip'
 myhostip=subprocess.run(cmdline.split(),stdout=subprocess.PIPE).stdout.decode('utf-8').replace('\n','').replace(' ','')
 if len(sys.argv[1:]) < 2:
    print(' syncing all groups')
    groupsyncall(*sys.argv[1:])
 else:
    onegroupsync(*sys.argv[1:])
