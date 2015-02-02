#!/usr/bin/env python

# Copyright 2012 - 2013 Red Hat, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

import sys

import rtslib

from cinder import i18n
from cinder.i18n import _

i18n.enable_lazy()


class RtstoolError(Exception):
    pass


class RtstoolImportError(RtstoolError):
    pass


def create(backing_device, name, userid, password, iser_enabled,
           initiator_iqns=None):
    try:
        rtsroot = rtslib.root.RTSRoot()
    except rtslib.utils.RTSLibError:
        print(_('Ensure that configfs is mounted at /sys/kernel/config.'))
        raise

    # Look to see if BlockStorageObject already exists
    for x in rtsroot.storage_objects:
        if x.name == name:
            # Already exists, use this one
            return

    so_new = rtslib.BlockStorageObject(name=name,
                                       dev=backing_device)

    target_new = rtslib.Target(rtslib.FabricModule('iscsi'), name, 'create')

    tpg_new = rtslib.TPG(target_new, mode='create')
    tpg_new.set_attribute('authentication', '1')

    lun_new = rtslib.LUN(tpg_new, storage_object=so_new)

    if initiator_iqns:
        initiator_iqns = initiator_iqns.strip(' ')
        for i in initiator_iqns.split(','):
            acl_new = rtslib.NodeACL(tpg_new, i, mode='create')
            acl_new.chap_userid = userid
            acl_new.chap_password = password

            rtslib.MappedLUN(acl_new, lun_new.lun, lun_new.lun)

    tpg_new.enable = 1

    try:
        portal = rtslib.NetworkPortal(tpg_new, '0.0.0.0', 3260, mode='any')
    except rtslib.utils.RTSLibError:
        print(_('Error creating NetworkPortal: ensure port 3260 '
                'is not in use by another service.'))
        raise

    try:
        if iser_enabled == 'True':
            portal._set_iser(1)
    except rtslib.utils.RTSLibError:
        print(_('Error enabling iSER for NetworkPortal: please ensure that '
                'RDMA is supported on your iSCSI port.'))
        raise

    try:
        rtslib.NetworkPortal(tpg_new, '::0', 3260, mode='any')
    except rtslib.utils.RTSLibError:
        # TODO(emh): Binding to IPv6 fails sometimes -- let pass for now.
        pass


def _lookup_target(target_iqn, initiator_iqn):
    try:
        rtsroot = rtslib.root.RTSRoot()
    except rtslib.utils.RTSLibError:
        print(_('Ensure that configfs is mounted at /sys/kernel/config.'))
        raise

    # Look for the target
    for t in rtsroot.targets:
        if t.wwn == target_iqn:
            return t
    raise RtstoolError(_('Could not find target %s') % target_iqn)


def add_initiator(target_iqn, initiator_iqn, userid, password):
    target = _lookup_target(target_iqn, initiator_iqn)
    tpg = target.tpgs.next()  # get the first one
    for acl in tpg.node_acls:
        # See if this ACL configuration already exists
        if acl.node_wwn == initiator_iqn:
            # No further action required
            return

    acl_new = rtslib.NodeACL(tpg, initiator_iqn, mode='create')
    acl_new.chap_userid = userid
    acl_new.chap_password = password

    rtslib.MappedLUN(acl_new, 0, tpg_lun=0)


def delete_initiator(target_iqn, initiator_iqn):
    target = _lookup_target(target_iqn, initiator_iqn)
    tpg = target.tpgs.next()  # get the first one
    for acl in tpg.node_acls:
        if acl.node_wwn == initiator_iqn:
            acl.delete()
            return
    raise RtstoolError(_('Could not find ACL %(acl)s in target %(target)s')
                       % {'target': target_iqn, 'acl': initiator_iqn})


def get_targets():
    rtsroot = rtslib.root.RTSRoot()
    for x in rtsroot.targets:
        print(x.wwn)


def delete(iqn):
    rtsroot = rtslib.root.RTSRoot()
    for x in rtsroot.targets:
        if x.wwn == iqn:
            x.delete()
            break

    for x in rtsroot.storage_objects:
        if x.name == iqn:
            x.delete()
            break


def verify_rtslib():
    for member in ['BlockStorageObject', 'FabricModule', 'LUN',
                   'MappedLUN', 'NetworkPortal', 'NodeACL', 'root',
                   'Target', 'TPG']:
        if not hasattr(rtslib, member):
            raise RtstoolImportError(_("rtslib is missing member %s: "
                                       "You may need a newer python-rtslib.") %
                                     member)


def usage():
    print("Usage:")
    print(sys.argv[0] +
          " create [device] [name] [userid] [password] [iser_enabled]" +
          " <initiator_iqn,iqn2,iqn3,...>")
    print(sys.argv[0] +
          " add-initiator [target_iqn] [userid] [password] [initiator_iqn]")
    print(sys.argv[0] +
          " delete-initiator [target_iqn] [initiator_iqn]")
    print(sys.argv[0] + " get-targets")
    print(sys.argv[0] + " delete [iqn]")
    print(sys.argv[0] + " verify")
    sys.exit(1)


def main(argv=None):
    if argv is None:
        argv = sys.argv

    if len(argv) < 2:
        usage()

    if argv[1] == 'create':
        if len(argv) < 7:
            usage()

        if len(argv) > 8:
            usage()

        backing_device = argv[2]
        name = argv[3]
        userid = argv[4]
        password = argv[5]
        iser_enabled = argv[6]
        initiator_iqns = None

        if len(argv) > 7:
            initiator_iqns = argv[7]

        create(backing_device, name, userid, password, iser_enabled,
               initiator_iqns)

    elif argv[1] == 'add-initiator':
        if len(argv) < 6:
            usage()

        target_iqn = argv[2]
        userid = argv[3]
        password = argv[4]
        initiator_iqn = argv[5]

        add_initiator(target_iqn, initiator_iqn, userid, password)

    elif argv[1] == 'delete-initiator':
        if len(argv) < 4:
            usage()

        target_iqn = argv[2]
        initiator_iqn = argv[3]

        delete_initiator(target_iqn, initiator_iqn)

    elif argv[1] == 'get-targets':
        get_targets()

    elif argv[1] == 'delete':
        if len(argv) < 3:
            usage()

        iqn = argv[2]
        delete(iqn)

    elif argv[1] == 'verify':
        # This is used to verify that this script can be called by cinder,
        # and that rtslib is new enough to work.
        verify_rtslib()
        return 0

    else:
        usage()

    return 0
