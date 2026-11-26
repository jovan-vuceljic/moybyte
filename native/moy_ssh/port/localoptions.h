// Dropbear's build options for the console (default_options.h names every
// one): a server only, one user, one connection at a time, inside the
// kernel's process. The algorithm set is the smallest an OpenSSH client
// accepts without being told anything: curve25519 key exchange, an ed25519
// host key, chacha20-poly1305; sign-in by password or an ed25519 key.

#ifndef MOY_SSH_LOCALOPTIONS_H
#define MOY_SSH_LOCALOPTIONS_H

#define DROPBEAR_MOY 1

#define DROPBEAR_SMALL_CODE 1
#define NON_INETD_MODE 1
#define INETD_MODE 0

#define DROPBEAR_X11FWD 0
#define DROPBEAR_SVR_LOCALTCPFWD 0
#define DROPBEAR_SVR_REMOTETCPFWD 0
#define DROPBEAR_SVR_LOCALSTREAMFWD 0
#define DROPBEAR_SVR_REMOTESTREAMFWD 0
#define DROPBEAR_SVR_AGENTFWD 0
#define DROPBEAR_CLI_LOCALTCPFWD 0
#define DROPBEAR_CLI_REMOTETCPFWD 0
#define DROPBEAR_CLI_AGENTFWD 0

#define DROPBEAR_AES128 0
#define DROPBEAR_AES256 0
#define DROPBEAR_CHACHA20POLY1305 1
#define DROPBEAR_ENABLE_CTR_MODE 0
#define DROPBEAR_ENABLE_CBC_MODE 0
#define DROPBEAR_ENABLE_GCM_MODE 0
#define DROPBEAR_SHA1_HMAC 0
#define DROPBEAR_SHA2_256_HMAC 1
#define DROPBEAR_SHA2_512_HMAC 0
#define DROPBEAR_SHA1_96_HMAC 0

#define DROPBEAR_RSA 0
#define DROPBEAR_RSA_SHA1 0
#define DROPBEAR_DSS 0
#define DROPBEAR_ECDSA 0
#define DROPBEAR_ED25519 1
#define DROPBEAR_SK_KEYS 0
#define DROPBEAR_DELAY_HOSTKEY 1

#define DROPBEAR_DH_GROUP14_SHA1 0
#define DROPBEAR_DH_GROUP14_SHA256 0
#define DROPBEAR_DH_GROUP16 0
#define DROPBEAR_CURVE25519 1
#ifndef DROPBEAR_MLKEM768
#define DROPBEAR_MLKEM768 0
#endif
#define DROPBEAR_SNTRUP761 0
#define DROPBEAR_ECDH 0
#define DROPBEAR_DH_GROUP1 0

#define DO_HOST_LOOKUP 0
#define DO_MOTD 0
#define DROPBEAR_SVR_PASSWORD_AUTH 1
#define DROPBEAR_SVR_PAM_AUTH 0
#define DROPBEAR_SVR_PUBKEY_AUTH 1
#define DROPBEAR_SVR_PUBKEY_OPTIONS 0
#define DROPBEAR_SVR_MULTIUSER 0
#define DROPBEAR_SVR_DROP_PRIVS 0
// The `sftp` subsystem is the command SFTPSERVER_PATH names, which
// moy_ssh_command opens as the face's SFTP server (native/moy_tty/moy_tty_sftp.c)
#define DROPBEAR_SFTPSERVER 1
#define SFTPSERVER_PATH "internal-sftp"
#define DROPBEAR_PLUGIN 0
#define LOG_COMMANDS 0
#define UNAUTH_CLOSE_DELAY 0
#define MAX_AUTH_TRIES 5
// The server serves one connection at a time (moy_ssh_serve_one), so one
// that never signs in holds SSH for this long: 30 s from the connect, enough
// to accept the host key and type the password.
#define AUTH_TIMEOUT 30

#define DROPBEAR_DEFPORT "22"
// The host key is never read from a file: setup takes its bytes (moy_ssh.h).
#define ED25519_PRIV_FILENAME "/moy_ssh/no-key-file"
#define DEFAULT_PATH "/bin"
#define DEFAULT_ROOT_PATH "/bin"

// The session's buffers: a window of 8 KB the client may send ahead, and 2 KB
// on a board without PSRAM, where the channel's buffer of that size, made at
// the client's first bytes, is a block of the internal heap a session has
// little of (the C3 Zero's interactive session ended at its first key).
// There the packets the server sends are at most 2 KB too: the payload
// buffer of that size is held for the whole session (and a second one by a
// sign-in taking over, beside the served session's: moy_ssh.c, THE
// TAKEOVER), each packet is a block its size, and the queue to the client
// takes about three before the server stops reading the face
// (common-session.c); Dropbear's 16 KB held 16 KB from the sign-in on and let
// the queue reach 48 KB. The largest packet besides a channel's data is the
// key exchange's, well under 2 KB with curve25519 and an ed25519 key.
#include "moy_platform.h"
#if defined(MOY_ON_BOARD) && !defined(MOY_HAS_PSRAM)
#define DEFAULT_RECV_WINDOW 2048
#define TRANS_MAX_PAYLOAD_LEN 2048
#else
#define DEFAULT_RECV_WINDOW 8192
#endif

// The port's names for what a POSIX system has (port/moy_ssh_port.c).
#include "moy_ssh_port.h"

#endif // MOY_SSH_LOCALOPTIONS_H
