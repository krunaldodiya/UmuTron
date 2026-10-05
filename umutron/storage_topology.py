"""Conservative, read-only internal-partition provenance. No privileged helper."""
import os
from pathlib import Path
import re

BLOCK='org.freedesktop.UDisks2.Block'
PARTITION='org.freedesktop.UDisks2.Partition'
DRIVE='org.freedesktop.UDisks2.Drive'
UNKNOWN='Internal attachment could not be verified. This partition is unavailable.'
EXTERNAL='External, removable and hot-plug drives are not supported.'
LIMITED='PCIe attachment details are unavailable. Registration only; automatic downloads and installation remain unavailable.'
PCI=re.compile(r'[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]')


def small_text(path):
    with path.open() as stream:value=stream.read(4097)
    if len(value)>4096:raise ValueError('Oversized device property')
    return value.strip()


def pci_port_internal(data):
    """Require readable PCIe slot capabilities; truncated config is unknown."""
    if len(data)<64: return None
    if not int.from_bytes(data[6:8],'little')&0x10:return None
    cursor=data[0x34]&0xfc;seen=set()
    while cursor:
        if cursor<64 or cursor in seen or cursor+2>len(data):return None
        seen.add(cursor)
        if data[cursor]==0x10:
            if cursor+4>len(data):return None
            flags=int.from_bytes(data[cursor+2:cursor+4],'little')
            if (flags>>4)&15 not in (4,6):return None
            if not flags&0x100:return True  # Explicit no-slot implementation.
            if cursor+24>len(data):return None
            slot=int.from_bytes(data[cursor+20:cursor+24],'little')
            return not bool(slot&((1<<6)|(1<<5)))  # Hot-plug capable/surprise.
        cursor=data[cursor+1]&0xfc
    return None


class InternalPartitions:
    def __init__(self,sysfs=Path('/sys')):self.sysfs=Path(sysfs)

    def __call__(self,interfaces,objects):
        try:return self.check(interfaces,objects)
        except (OSError,ValueError,KeyError,TypeError,OverflowError):return UNKNOWN

    def registration(self,interfaces,objects):
        """Separate metadata enrollment from proof required for managed writes."""
        try:reason=self.check(interfaces,objects,registration_only=True)
        except (OSError,ValueError,KeyError,TypeError,OverflowError):reason=UNKNOWN
        return ('',LIMITED) if reason==LIMITED else (reason,'')

    def check(self,interfaces,objects,*,registration_only=False):
        partition=interfaces.get(PARTITION)
        if not isinstance(partition,dict):return 'Choose a partition, not a whole disk or virtual device.'
        number=partition.get('Number')
        if type(number) is not int or number<1 or partition.get('IsContainer'):return UNKNOWN
        block=interfaces[BLOCK];parent=objects[partition['Table']][BLOCK]
        drive=objects[block['Drive']][DRIVE]
        if parent.get('Drive')!=block['Drive']:return UNKNOWN
        if drive.get('ConnectionBus') not in ('','ata','nvme'):return EXTERNAL
        if any(drive.get(k) is True for k in ('Removable','MediaRemovable','Ejectable','CanPowerOff')):return EXTERNAL
        if any(drive.get(k) is not False for k in ('Removable','MediaRemovable','Ejectable','CanPowerOff')):return UNKNOWN
        if block.get('HintSystem') is not True or parent.get('HintSystem') is not True:return UNKNOWN
        device=block['DeviceNumber'];parent_device=parent['DeviceNumber']
        if type(device) is not int or type(parent_device) is not int:return UNKNOWN
        def node(dev):return (self.sysfs/'dev/block'/f'{os.major(dev)}:{os.minor(dev)}').resolve(strict=True)
        part=node(device);disk=node(parent_device);devices=self.sysfs/'devices'
        if not part.is_relative_to(devices) or not disk.is_relative_to(devices):return UNKNOWN
        if part.parent!=disk or int(small_text(part/'partition'))!=number:return UNKNOWN
        if small_text(part/'dev')!=f'{os.major(device)}:{os.minor(device)}':return UNKNOWN
        if small_text(disk/'dev')!=f'{os.major(parent_device)}:{os.minor(parent_device)}':return UNKNOWN
        if small_text(disk/'removable')!='0':return EXTERNAL
        ancestors=[disk,*disk.parents]
        if any(re.match(r'(usb\d|thunderbolt|firewire|mmc|rport-|session\d|virtual)',p.name) for p in ancestors):return EXTERNAL
        pci=[p for p in reversed(ancestors) if PCI.fullmatch(p.name)]
        if not pci or not pci[0].parent.name.startswith('pci'):return UNKNOWN
        limited=False
        for port in pci[:-1]:
            if int(small_text(port/'class'),16)!=0x060400:return UNKNOWN
            # A missing/inaccessible capability is not evidence of a fixed port.
            with (port/'config').open('rb') as stream:data=stream.read(256)
            fixed=pci_port_internal(data)
            if fixed is False:return EXTERNAL
            if fixed is None:
                # Linux normally exposes only the 64-byte PCI header to an
                # unprivileged reader. This is not proof of a fixed port.
                # Permit metadata-only enrollment for a direct PCIe NVMe
                # endpoint after all remaining identity/transport checks;
                # never grant cache/archive authority or relax known denials.
                header_only=(len(data)==64 and data[0x0e]&0x7f==1
                    and int.from_bytes(data[6:8],'little')&0x10 and data[0x34]&0xfc>=64)
                if not (registration_only and len(pci)==2 and header_only):return UNKNOWN
                limited=True
        endpoint=pci[-1];kind=int(small_text(endpoint/'class'),16)
        if kind==0x010601:
            if limited:return UNKNOWN
            hosts=[p for p in ancestors if re.fullmatch(r'host\d+',p.name)]
            atas=[p for p in ancestors if re.fullmatch(r'ata\d+',p.name)]
            if len(hosts)!=1 or len(atas)!=1 or atas[0].parent!=endpoint:return UNKNOWN
            host=self.sysfs/'class/scsi_host'/hosts[0].name
            if host.resolve(strict=True).parent.parent!=hosts[0]:return UNKNOWN
            if small_text(host/'proc_name')!='ahci':return UNKNOWN
            flags=int(small_text(host/'ahci_port_cmd'),16)
            if not 0<=flags<2**32:return UNKNOWN
            # AHCI ESP, HPCP, MPSP, CPD and PMP: conservative external/hotplug
            # or multi-device topology rejection, including direct eSATA.
            if flags&sum(1<<bit for bit in (17,18,19,20,21)):return EXTERNAL
            return ''
        if kind==0x010802:
            controllers=[p for p in ancestors if re.fullmatch(r'nvme\d+',p.name)]
            if len(controllers)!=1 or controllers[0].parent.name!='nvme' or controllers[0].parent.parent!=endpoint:return UNKNOWN
            if small_text(controllers[0]/'transport')!='pcie':return EXTERNAL
            return LIMITED if limited else ''
        return UNKNOWN
