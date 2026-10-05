"""Synthetic sysfs/DBus fixtures only; no device operations."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest

from game_library.storage_topology import BLOCK,DRIVE,PARTITION,InternalPartitions,pci_port_internal,LIMITED


def config(hotplug=False):
    data=bytearray(256);data[6]=0x10;data[0x34]=0x40;data[0x40]=0x10
    data[0x42:0x44]=(0x140).to_bytes(2,'little')
    data[0x54:0x58]=((1<<6) if hotplug else 0).to_bytes(4,'little')
    return data


class TopologyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.pci=self.root/'devices/pci0000:00/0000:00:17.0'
        self.disk=self.pci/'ata3/host2/target2:0:0/2:0:0:0/block/sda'
        self.part=self.disk/'sda2';self.part.mkdir(parents=True)
        self.write(self.pci/'class','0x010601');self.write(self.disk/'dev','8:0');self.write(self.disk/'removable','0')
        self.write(self.part/'dev','8:2');self.write(self.part/'partition','2')
        host=self.pci/'ata3/host2/scsi_host/host2';host.mkdir(parents=True)
        self.write(host/'proc_name','ahci');self.write(host/'ahci_port_cmd','c017')
        self.host=host
        self.link(self.root/'class/scsi_host/host2',host)
        self.link(self.root/'dev/block/8:0',self.disk);self.link(self.root/'dev/block/8:2',self.part)
        self.interfaces={BLOCK:{'DeviceNumber':os.makedev(8,2),'Drive':'/drive','HintSystem':True},
                         PARTITION:{'Number':2,'Table':'/disk','IsContainer':False}}
        self.objects={'/disk':{BLOCK:{'DeviceNumber':os.makedev(8,0),'Drive':'/drive','HintSystem':True}},
                      '/drive':{DRIVE:{'ConnectionBus':'','Removable':False,'MediaRemovable':False,'Ejectable':False,'CanPowerOff':False}}}
        self.check=InternalPartitions(self.root)

    def write(self,path,text):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    def link(self,path,target):path.parent.mkdir(parents=True,exist_ok=True);path.symlink_to(target)
    def reason(self):return self.check(self.interfaces,self.objects)

    def test_internal_ahci_partition_has_positive_port_evidence(self):self.assertEqual(self.reason(),'')

    def test_esata_hotplug_multiplier_and_presence_ports_are_rejected(self):
        for bit in (17,18,19,20,21):
            self.write(self.host/'ahci_port_cmd',hex(1<<bit))
            with self.subTest(bit=bit):self.assertIn('External',self.reason())

    def test_ata_or_nonremovable_hint_alone_is_not_enough(self):
        (self.host/'ahci_port_cmd').unlink();self.assertIn('could not be verified',self.reason())

    def test_usb_firewire_and_unknown_bus_and_drive_flags(self):
        original=deepcopy(self.objects['/drive'][DRIVE])
        for bus in ('usb','ieee1394','sdio','unknown'):
            self.objects['/drive'][DRIVE]={**original,'ConnectionBus':bus};self.assertTrue(self.reason())
        for flag in ('Removable','MediaRemovable','Ejectable','CanPowerOff'):
            self.objects['/drive'][DRIVE]={**original,flag:True};self.assertIn('External',self.reason())
            self.objects['/drive'][DRIVE]={**original};del self.objects['/drive'][DRIVE][flag];self.assertIn('could not',self.reason())

    def test_whole_disk_virtual_and_mismatched_partition_fail_closed(self):
        original=deepcopy(self.interfaces)
        self.interfaces.pop(PARTITION);self.assertIn('partition',self.reason())
        self.interfaces=original;self.interfaces[PARTITION]['Number']=3;self.assertTrue(self.reason())
        self.interfaces[PARTITION]['Number']=2;self.objects['/disk'][BLOCK]['Drive']='/other';self.assertTrue(self.reason())

    def test_second_partition_on_same_disk_and_mount_path_do_not_change_eligibility(self):
        # Provenance intentionally does not examine any mountpoint spelling.
        self.interfaces['mount_path']='/run/media/user/Games';self.assertFalse(self.reason())
        part=self.disk/'sda3';part.mkdir();self.write(part/'dev','8:3');self.write(part/'partition','3')
        self.link(self.root/'dev/block/8:3',part)
        self.interfaces[BLOCK]['DeviceNumber']=os.makedev(8,3);self.interfaces[PARTITION]['Number']=3
        self.assertFalse(self.reason())

    def test_pcie_capability_requires_explicit_readable_fixed_port(self):
        self.assertTrue(pci_port_internal(config()));self.assertFalse(pci_port_internal(config(True)))
        for data in (b'',bytes(64),config()[:64],config()[:80]):self.assertIsNone(pci_port_internal(data))
        malformed=config();malformed[0x40]=0;malformed[0x41]=0x40;self.assertIsNone(pci_port_internal(malformed))

    def nvme(self):
        bridge=self.root/'devices/pci0000:00/0000:00:1d.0';endpoint=bridge/'0000:0d:00.0'
        disk=endpoint/'nvme/nvme0/nvme0n1';part=disk/'nvme0n1p5';part.mkdir(parents=True)
        self.write(bridge/'class','0x060400');(bridge/'config').write_bytes(config())
        self.write(endpoint/'class','0x010802');self.write(endpoint/'nvme/nvme0/transport','pcie')
        self.write(disk/'dev','259:0');self.write(disk/'removable','0');self.write(part/'dev','259:1');self.write(part/'partition','5')
        self.link(self.root/'dev/block/259:0',disk);self.link(self.root/'dev/block/259:1',part)
        self.interfaces[BLOCK]['DeviceNumber']=os.makedev(259,1);self.interfaces[PARTITION]['Number']=5
        self.objects['/disk'][BLOCK]['DeviceNumber']=os.makedev(259,0)
        return bridge

    def test_fixed_pcie_nvme_and_hotplug_tunnel_ancestry(self):
        bridge=self.nvme();self.assertFalse(self.reason())
        (bridge/'config').write_bytes(config(True));self.assertIn('External',self.reason())
        (bridge/'config').write_bytes(config()[:64]);self.assertIn('could not',self.reason())

    def test_symlinked_kernel_parent_mismatch_rejected(self):
        (self.root/'dev/block/8:0').unlink();self.link(self.root/'dev/block/8:0',self.root/'unknown')
        self.assertTrue(self.reason())

    def test_header_only_direct_nvme_registers_without_managed_authority(self):
        bridge=self.nvme();data=config();data[0x0e]=1
        (bridge/'config').write_bytes(data[:64])
        self.assertIn('could not',self.reason())
        self.assertEqual(self.check.registration(self.interfaces,self.objects),('',LIMITED))

    def test_registration_keeps_positive_fixed_and_hotplug_results(self):
        bridge=self.nvme()
        self.assertEqual(self.check.registration(self.interfaces,self.objects),('',''))
        (bridge/'config').write_bytes(config(True))
        reason,limited=self.check.registration(self.interfaces,self.objects)
        self.assertIn('External',reason);self.assertFalse(limited)

    def test_registration_does_not_accept_other_missing_or_malformed_capabilities(self):
        bridge=self.nvme();good=config();good[0x0e]=1
        bad_header=bytearray(good[:64]);bad_header[0x0e]=0
        no_cap=bytearray(good[:64]);no_cap[6]=0
        no_pointer=bytearray(good[:64]);no_pointer[0x34]=0
        for data in (b'',good[:63],good[:65],bad_header,no_cap,no_pointer):
            with self.subTest(data=bytes(data)):
                (bridge/'config').write_bytes(data)
                reason,limited=self.check.registration(self.interfaces,self.objects)
                self.assertIn('could not',reason);self.assertFalse(limited)
        (bridge/'config').unlink()
        self.assertIn('could not',self.check.registration(self.interfaces,self.objects)[0])

    def test_limited_registration_still_checks_every_nvme_identity_and_transport(self):
        bridge=self.nvme();data=config();data[0x0e]=1;(bridge/'config').write_bytes(data[:64])
        original=deepcopy(self.objects['/drive'][DRIVE])
        for field,value in [('ConnectionBus','usb'),('Removable',True),('MediaRemovable',True),('Ejectable',True),('CanPowerOff',True)]:
            self.objects['/drive'][DRIVE]={**original,field:value}
            self.assertIn('External',self.check.registration(self.interfaces,self.objects)[0])
        self.objects['/drive'][DRIVE]=original
        transport=bridge/'0000:0d:00.0/nvme/nvme0/transport'
        transport.write_text('tcp')
        self.assertIn('External',self.check.registration(self.interfaces,self.objects)[0])
        transport.write_text('pcie');self.interfaces[PARTITION]['Number']=6
        self.assertIn('could not',self.check.registration(self.interfaces,self.objects)[0])
