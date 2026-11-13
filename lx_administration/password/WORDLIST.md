# Passphrase vocabulary

`eff_short_wordlist_1.txt` is an unchanged copy of the Electronic Frontier
Foundation's **general short wordlist**, published September 8, 2016, downloaded
November 2, 2026:

- [Canonical wordlist](https://www.eff.org/files/2016/09/08/eff_short_wordlist_1.txt)
- [EFF's construction and entropy explanation](https://www.eff.org/deeplinks/2016/07/new-wordlists-random-passphrases)
- [EFF copyright policy](https://www.eff.org/copyright)
- [CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/)

Copyright Electronic Frontier Foundation, used under Creative Commons
Attribution 4.0 International. EFF does not endorse this implementation.
The upstream file is preserved byte for byte. SHA-256:
`8f5ca830b8bffb6fe39c9736c024a00a6a6411adb3f83a9be8bfeeb6e067ae69`.

The loader validates that digest and all 1,296 unique entries. Spaces separate
words so that the distinct original entries `yo-yo` and `yoyo` remain distinct.
No entry is normalized, filtered or frequency weighted.
Each word is chosen independently with `secrets.choice`.

The fixed floor is 128 bits from the words alone: 13 words provide
`13 * log2(1296)`, approximately **134.42 bits**. `num_words` is a requested
minimum and is raised to 13 when necessary. Additional independent words meet
`min_length`. Required digits and punctuation are suffixes, never replacements
for words, and do not contribute to the claimed entropy floor. Required upper
case capitalizes the first word reversibly; other words remain lowercase.
Disabling a case requirement does not forbid that case in a passphrase.

Missing or altered package data is an error. Generating a new credential does
not rotate or replace existing credentials; credential-family rotation requires
separate reviewed custody, readback and rollback procedures.
