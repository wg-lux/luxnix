# Security 

For security reasons, the ssh keys as well as passwords and usernames will be encrypted using LUKS linux standard encryption.

## Keyfile and LUKS setup

To explore all registered keyfiles for your LUKS-encrypted devices and remove old ones, you can use the cryptsetup tool. Here's how you can manage this:
1. Listing Registered Keyslots/Keyfiles

LUKS stores keys in keyslots. To see all the keyslots (which can contain passphrases or keyfiles) of a LUKS device, you can use the cryptsetup luksDump command:

```bash
    sudo cryptsetup luksDump /dev/sdX
    sudo cryptsetup luksRemoveKey /dev/sdX --key-file /path/to/old-keyfile
```

Replace /dev/sdX with the actual device path of your LUKS-encrypted device (for example, /dev/sda1, /dev/nvme0n1p1, etc.).

This will output information about the LUKS header, including the keyslots. If a keyslot is active (i.e., contains a valid key), it will be listed. The output will look something like this:

LUKS header information for /dev/sdX

Version:        2
Epoch:          1
Keyslots:
  0: ENABLED
        Key Size:  512 bits
        Priority:  normal
  1: DISABLED
  2: DISABLED
  3: ENABLED
        Key Size:  512 bits
        Priority:  high
...

    ENABLED keyslots are active and contain a valid key or keyfile.
    DISABLED keyslots are inactive and don't contain a valid key.

2. Removing Old Keyfiles/Keyslots

To remove a key from a keyslot, use the cryptsetup luksRemoveKey command. You can either remove a specific keyfile or passphrase.

    If you want to remove a keyfile, use the following command:

sudo cryptsetup luksRemoveKey /dev/sdX --key-file /path/to/old-keyfile

Replace /path/to/old-keyfile with the actual path to the keyfile and /dev/sdX with your device.

    If you want to remove a passphrase, the command will prompt you for the passphrase to remove:

sudo cryptsetup luksRemoveKey /dev/sdX

3. Removing A Specific Keyslot by Slot Number

If you know which keyslot corresponds to an old key you want to remove (for example, from the luksDump output), you can remove it by specifying the keyslot number directly:

sudo cryptsetup luksKillSlot /dev/sdX N

Replace N with the keyslot number you want to remove.
Example: Exploring and Removing Old Keyfiles

    List all keyslots:

    sudo cryptsetup luksDump /dev/nvme0n1p1

    Remove a keyfile in keyslot 1:

    sudo cryptsetup luksRemoveKey /dev/nvme0n1p1 --key-file /etc/keys/old-keyfile

    Remove the key in keyslot 2 directly:

    sudo cryptsetup luksKillSlot /dev/nvme0n1p1 2

By following these steps, you can manage the keyslots for your LUKS devices, exploring existing keyfiles and removing outdated ones.
