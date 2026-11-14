#!/bin/sh
######################
#exit
##########################
cd /pace
# the trace without the CHAP secret ($7)
echo $@ | awk '{ if (NF >= 7) $7 = "***"; print }' > /root/addzfsvol
#/pace/addzfsvolumeastarget.sh $pool'/'${vol} $ipaddr $portalport $targetiqn $chapuser $chappas
pool=`echo $@ | awk '{print $1}'`
vol=`echo $@ | awk '{print $2}'`
ipaddr=`echo $@ | awk '{print $3}'`
portalport=`echo $@ | awk '{print $4}'`
target=`echo $@ | awk '{print $5}'`
chapuser=`echo $@ | awk '{print $6}'`
chappas=`echo $@ | awk '{print $7}'`
lunid=`echo $@ | awk '{print $8}'`
# container flavour: no udev, the zvol node and its /dev/zvol link are made here (see czvoldev.sh)
[ -f /TopStor/flavor.sh ] && . /TopStor/flavor.sh
is_container 2>/dev/null && /pace/czvoldev.sh
disk=`ls -l /dev/zvol/${pool}/$vol | awk -F'/' '{print $NF}'`
echo disk $disk
#chapuser='iqn.1991-05.com.microsoft:desktop-jckvhk3'
myhost=`hostname -s`;
change=0
#declare -a iscsitargets=(`cat /pacedata/iscsitargets | awk '{print $2}' `;
#target='iqn.1991-05.com.microsoft:desktop-jckvhk3'
#target='iqn.1994-05.com.redhat:dhcp13038'
#disk='zd0'
ipdom=`echo $ipaddr | sed 's/\.//g'`
diskids=$disk'-'$myhost'-'$vol
iqn='.2016-03.com.'$ipdom':data'
targetcli ls iscsi/ | grep ".$ipdom:data" &>/dev/null
if [ $? -ne 0 ]; then
 targetcli iscsi/ create iqn.2016-03.com.${ipdom}:data &>/dev/null
fi
pdisk=`targetcli ls backstores/block 1 | awk '{print $2}'`
# a zvol exported as a cluster disk (<disk>-<host>, made by an older disk exporter) holds the zvol: remove it
echo "$pdisk" | grep -qx "${disk}-${myhost}" && targetcli backstores/block delete ${disk}-${myhost}
# the exact backstore name: 'grep $disk' also matched zd1 in zd16-... or zd0 in zd0-<host> and the volume got no LUN
echo "$pdisk" | grep -qx "$diskids"
if [ $? -ne 0 ];
then 
 targetcli backstores/block create $diskids /dev/$disk
 echo targetcli backstores/block create $diskids /dev/$disk
fi
#tpg='tpg'$portalport
tpg='tpg1'

#targetcli iscsi/iqn${iqn} create $portalport  
targetcli iscsi/iqn${iqn} set global auto_add_mapped_luns=false
targetcli iscsi/iqn.2016-03.com.$ipdom:data/${tpg}/portals delete 0.0.0.0 3260
# QSD5.340 (test 650): one TPG LUN per backstore. It was created again on every call (one call per initiator, and again by
# VolumeChangeISCSI), so the volume could appear twice on the target under another LUN number.
targetcli ls iscsi/iqn${iqn}/${tpg}/luns 1 2>/dev/null | grep -qF "[block/$diskids "
[ $? -ne 0 ] && targetcli iscsi/iqn${iqn}/${tpg}/luns/ create /backstores/block/$diskids
# no initiator (This_lun_is_not_mapped from the UI, or empty): the LUN is on the target, no node ACL is made for it
echo "$target" | grep -Eiq '^(iqn|eui|naa)\.'
if [ $? -eq 0 ];
then
targetcli iscsi/iqn${iqn}/${tpg}/acls/ create $target
echo targetcli iscsi/iqn${iqn}/${tpg}/acls/ create $target
cluns=`targetcli iscsi/iqn${iqn}/${tpg}/acls/$target ls`
echo $cluns | grep $diskids 
if [ $? -ne 0 ];
then
 # the lowest mapped_lun number not used yet by this initiator (a count gave a used number once a lower one was deleted)
 used=`echo "$cluns" | grep -o 'mapped_lun[0-9]*' | sed 's/mapped_lun//'`
 nextlun=0
 while echo "$used" | grep -qx $nextlun; do nextlun=$((nextlun+1)); done
 echo targetcli iscsi/iqn${iqn}/${tpg}/acls/$target = $nextlun
 targetcli iscsi/iqn${iqn}/${tpg}/acls/$target create mapped_lun=$nextlun tpg_lun_or_backstore=/backstores/block/$diskids write_protect=0
 echo targetcli iscsi/iqn${iqn}/${tpg}/acls/$target create mapped_lun=$nextlun tpg_lun_or_backstore=/backstores/block/$diskids write_protect=0
fi
fi
targetcli iscsi/iqn${iqn}/${tpg} set attribute demo_mode_write_protect=0 
targetcli iscsi/iqn${iqn}/${tpg} set attribute cache_dynamic_acls=1
# only the initiators listed on the LUN (the acls created above) may log in: generate_node_acls=1 gave every other IQN a dynamic ACL with all LUNs mapped
targetcli iscsi/iqn${iqn}/${tpg} set attribute generate_node_acls=0
# QSD5.341 (test 653 QX-054): CHAP on the node ACL of the initiator (the requested pair, chappas encrypted by fapi), and
# authentication=1 while an ACL of the TPG has CHAP. It was 'set auth' on the TPG (used by generated ACLs only, which are
# off) with authentication=0: CHAP was never asked, and the secret was on the targetcli command line (~/.targetcli/log.txt).
/pace/iscsichap.sh iqn${iqn} "$chapuser" "$chappas" $target
targetcli iscsi/iqn.2016-03.com.$ipdom:data/${tpg}/portals create $ipaddr $portalport 
targetcli saveconfig
 #targetcli saveconfig /pacedata/targetconfig
