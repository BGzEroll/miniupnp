/* Test-only LD_PRELOAD interposer. No fault hook is built into MiniUPnPd. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/netfilter/nf_tables.h>
#include <linux/netfilter/nfnetlink.h>
#include <linux/netlink.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <unistd.h>

struct mnl_socket;
typedef ssize_t (*send_fn)(const struct mnl_socket *, const void *, size_t);
typedef ssize_t (*recv_fn)(const struct mnl_socket *, void *, size_t);
static int lose_ack;

ssize_t mnl_socket_sendto(const struct mnl_socket *socket, const void *data, size_t size)
{
	static send_fn original;
	struct nlmsghdr *message;
	int remaining = size, deletes = 0, flags[2] = {0, 0};
	char mode[64] = {0};
	int fd;
	if (!original) original = (send_fn)dlsym(RTLD_NEXT, "mnl_socket_sendto");
	fd = open("/tmp/upnp-delete-fault.mode", O_RDONLY);
	if (fd >= 0) { read(fd, mode, sizeof(mode) - 1); close(fd); }
	for (message = (struct nlmsghdr *)data; NLMSG_OK(message, remaining);
	     message = NLMSG_NEXT(message, remaining)) {
		unsigned type = message->nlmsg_type;
		if ((type >> 8) != NFNL_SUBSYS_NFTABLES) continue;
		if ((type & 255) == NFT_MSG_GETRULE && strncmp(mode, "dump", 4) == 0) {
			errno = EIO; return -1;
		}
		if ((type & 255) != NFT_MSG_DELRULE) continue;
		if (deletes < 2) flags[deletes] = message->nlmsg_flags;
		deletes++;
		if ((strncmp(mode, "first", 5) == 0 && deletes == 1) ||
		    (strncmp(mode, "second", 6) == 0 && deletes == 2) ||
		    strncmp(mode, "handle:", 7) == 0) {
			struct nlattr *attr = (void *)((char *)NLMSG_DATA(message) + sizeof(struct nfgenmsg));
			int length = message->nlmsg_len - NLMSG_HDRLEN - sizeof(struct nfgenmsg);
			while (length >= (int)sizeof(*attr) && attr->nla_len >= sizeof(*attr) && attr->nla_len <= length) {
				if ((attr->nla_type & NLA_TYPE_MASK) == NFTA_RULE_HANDLE && attr->nla_len >= sizeof(*attr) + 8) {
					unsigned char *value = (void *)((char *)attr + sizeof(*attr));
					unsigned long long handle = 0;
					unsigned i;
					for (i = 0; i < 8; i++) handle = (handle << 8) | value[i];
					if (strncmp(mode, "handle:", 7) || handle == strtoull(mode + 7, NULL, 10))
						memset(value, 255, 8);
				}
				length -= NLA_ALIGN(attr->nla_len);
				attr = (void *)((char *)attr + NLA_ALIGN(attr->nla_len));
			}
		}
	}
	if (deletes) {
		if (strncmp(mode, "ackloss", 7) == 0) lose_ack = 1;
		FILE *trace = fopen("/tmp/upnp-delete-fault.trace", "a");
		if (trace) { fprintf(trace, "%d %d %d\n", deletes, flags[0], flags[1]); fclose(trace); }
		if (strncmp(mode, "send", 4) == 0) { errno = EIO; return -1; }
		if (strncmp(mode, "race", 4) == 0) {
			unsigned i;
			fd = open("/tmp/upnp-delete-fault.ready", O_WRONLY | O_CREAT | O_TRUNC, 0600);
			if (fd >= 0) close(fd);
			/* The independent root test process performs the flush. The
			 * daemon drops exec-time capabilities, so an nft child cannot. */
			for (i = 0; i < 300 && access("/tmp/upnp-delete-fault.resume", F_OK); i++)
				usleep(10000);
		}

	}
	return original(socket, data, size);
}

ssize_t mnl_socket_recvfrom(const struct mnl_socket *socket, void *buffer, size_t length)
{
	static recv_fn original;
	ssize_t received;
	if (!original) original = (recv_fn)dlsym(RTLD_NEXT, "mnl_socket_recvfrom");
	received = original(socket, buffer, length);
	if (lose_ack) {
		lose_ack = 0;
		errno = EIO;
		return -1;
	}
	return received;
}
