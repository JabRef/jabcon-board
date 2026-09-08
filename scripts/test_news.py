#!/usr/bin/env python3
"""Self-check for the newsticker feed parser (RSS and Atom). Run: python3 scripts/test_news.py"""
import collect

RSS = b'<rss><channel><title>chan</title><item><title>A  b</title><link>http://x/a</link></item><item><title>no link</title></item></channel></rss>'
ATOM = b'<feed xmlns="http://www.w3.org/2005/Atom"><title>f</title><entry><title>C</title><link rel="alternate" href="http://x/c"/><link rel="self" href="http://x/self"/></entry></feed>'
assert collect.headlines(RSS) == [("A b", "http://x/a")]
assert collect.headlines(ATOM) == [("C", "http://x/c")]
print("ok")
