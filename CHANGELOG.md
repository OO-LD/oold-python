# CHANGELOG

All notable changes to this project are documented here. Versions are cut
automatically from Conventional Commits on every merge to main by
[python-semantic-release](https://python-semantic-release.readthedocs.io/). Do
not edit released sections by hand.

<!-- version list -->

## v0.18.1 (2026-08-27)

### Bug Fixes

- **validation**: Count a scoped @context term only where it is a property
  ([#135](https://github.com/OO-LD/oold-python/pull/135),
  [`0b49605`](https://github.com/OO-LD/oold-python/commit/0b49605e71d9bad5c25cf62ded4475512d9a4e2c))

### Code Style

- Apply ruff format to the new test ([#135](https://github.com/OO-LD/oold-python/pull/135),
  [`0b49605`](https://github.com/OO-LD/oold-python/commit/0b49605e71d9bad5c25cf62ded4475512d9a4e2c))

### Continuous Integration

- Gate the parity check against the reference
  ([`fdb9007`](https://github.com/OO-LD/oold-python/commit/fdb9007377aab115da3b2661e59834090af79314))

### Documentation

- **validation**: State invariants in comments, not prior behaviour
  ([`4baf212`](https://github.com/OO-LD/oold-python/commit/4baf212f85a6f97fc9f6f16eee07ab2a0bcd42d5))


## v0.18.0 (2026-08-24)

### Features

- **validation**: Accept a checkout as a meta-schema source
  ([`7a1030e`](https://github.com/OO-LD/oold-python/commit/7a1030e399fc0a5a72f9035d8c7a456974151fff))


## v0.17.1 (2026-08-24)

### Bug Fixes

- **validation**: Classify every level, and cite the coverage rule
  ([`be47619`](https://github.com/OO-LD/oold-python/commit/be47619ebbd3840882045965aaa1da684394fd35))

### Chores

- **meta**: Vendor oold-schema v1.0.0-rc.3
  ([`2485f98`](https://github.com/OO-LD/oold-python/commit/2485f98c6b5edb4a0af580f4c5be54f98e3a794a))

### Testing

- **validation**: Cover the unclassified-level raise
  ([`f509f3c`](https://github.com/OO-LD/oold-python/commit/f509f3c4f5a0cd1067a51e5849151916a7a05e18))


## v0.17.0 (2026-08-23)

### Bug Fixes

- **cli**: Keep the missing-extra guard on oold-validate
  ([`b4e23ac`](https://github.com/OO-LD/oold-python/commit/b4e23ac96a9bf50b61a6a84300c713025af75e96))

- **docs**: Restate and guard Zensical's default Markdown extensions
  ([`ebc3907`](https://github.com/OO-LD/oold-python/commit/ebc3907cae24a685b78edcd856ca514331148a95))

- **validation**: Count x-oold-context synonyms as mapped terms
  ([`7875b51`](https://github.com/OO-LD/oold-python/commit/7875b51b1e71f5b0fe1565009eef07eab2d8cfff))

- **validation**: Import select_rules where the MCP server uses it
  ([`7050e8b`](https://github.com/OO-LD/oold-python/commit/7050e8bc577a47f4b5478ca980ce4f7b37442017))

- **validation**: Keep a processor failure distinct from a missing term
  ([`2a03e2f`](https://github.com/OO-LD/oold-python/commit/2a03e2fae24fd52e61d488dc8b70149c677ed7db))

- **validation**: Report the keyword coverage.vocab leaves out
  ([`c5d9324`](https://github.com/OO-LD/oold-python/commit/c5d93248b0a13363f58f9beb816121f229d6e9e9))

- **validation**: Share rule filtering, report a corrupt rules schema
  ([`65d2ce3`](https://github.com/OO-LD/oold-python/commit/65d2ce33e5bd2d11ffee227a4e0cf3413a88310c))

- **validation**: Warn on an unmapped term instead of failing
  ([`561d0b8`](https://github.com/OO-LD/oold-python/commit/561d0b8258108252ae3767136726f0a3196ab807))

### Chores

- Ignore the local graphify-out directory
  ([`ef375d3`](https://github.com/OO-LD/oold-python/commit/ef375d379edcb81cb65f627cf5e72fd09b4ec967))

- **validation**: Vendor the 43-rule catalogue
  ([`cbcf95a`](https://github.com/OO-LD/oold-python/commit/cbcf95a3042c41078c7b670de4ce77b21db36a31))

### Code Style

- Apply ruff-format to the check-registry drift test
  ([`ca11109`](https://github.com/OO-LD/oold-python/commit/ca1110907aa194b32458cfb90599c4b8a51609b5))

- **tests**: Store the hand-written fixtures with LF line endings
  ([`8c965d6`](https://github.com/OO-LD/oold-python/commit/8c965d6cd3aea4963e709fc05e304e789aa73995))

### Documentation

- Add CLAUDE.md with the conventions agents keep getting wrong
  ([`4fdda5e`](https://github.com/OO-LD/oold-python/commit/4fdda5e796089c4950437918d212c802b4e2e8b4))

- Explain how to turn a specification rule into a check
  ([`988bc38`](https://github.com/OO-LD/oold-python/commit/988bc38de68724a027268721fad8818786bd5184))

- Fix the vendoring procedure and say what a new check owes
  ([`92524af`](https://github.com/OO-LD/oold-python/commit/92524af7fd721819d8d0874757d23dcfbdc6ba92))

- Move documentation out of source dirs and drop meta-talk
  ([`fc4de8c`](https://github.com/OO-LD/oold-python/commit/fc4de8c944bb4dcb238645b25cc45fb968b29d28))

- **spec**: Collapse the check mappings into one registry structure
  ([`264d71e`](https://github.com/OO-LD/oold-python/commit/264d71e300095719cdfe52c86726fb5bb64888e1))

- **spec**: Correct the version gate, and cost out a changed rule
  ([`08b9945`](https://github.com/OO-LD/oold-python/commit/08b9945ea338c3a261eb08d28e82b2d2b7a062ea))

- **spec**: Design a check registry and an `oold checks` command
  ([`26ceba9`](https://github.com/OO-LD/oold-python/commit/26ceba9c63a9170baaa376c63b039ebfa666a100))

- **spec**: Pin where compatibility for a new rule's check lives
  ([`3ba00a6`](https://github.com/OO-LD/oold-python/commit/3ba00a6ddff0aa3c739f6739ae7b76b1b11ffda2))

- **spec**: State which ids the registry covers, and fix the grep guard
  ([`3b497b5`](https://github.com/OO-LD/oold-python/commit/3b497b586ed1e8b13699263b492a27e1acdb1141))

- **validation**: Record catalogue's source so a rebase cannot orphan it
  ([`5bcd043`](https://github.com/OO-LD/oold-python/commit/5bcd043721226b48280e7980890264df9cdc623b))

### Features

- **validation**: Accept raw JSON in every MCP document tool
  ([`18a952c`](https://github.com/OO-LD/oold-python/commit/18a952c0d9994410d6b3a63e4da7c7bc3ab79762))

- **validation**: Add native OO-LD schema and instance validator
  ([`80ee29a`](https://github.com/OO-LD/oold-python/commit/80ee29a1c61cb429f8f39d8db70375508f7a8375))

- **validation**: Check catalogue and fixture slice against facts
  ([`a7a7f3c`](https://github.com/OO-LD/oold-python/commit/a7a7f3cd167e24e38731a117ad9a87494acbd666))

- **validation**: Cite the specification's rule ids in findings
  ([`f39b280`](https://github.com/OO-LD/oold-python/commit/f39b28057f24609789b5718099579fcffb49d560))

- **validation**: Classify a single file from its $schema
  ([`6897095`](https://github.com/OO-LD/oold-python/commit/6897095a29de18f612b16625ddfbb4a7469fed60))

- **validation**: Drive rule checks from the specification catalogue
  ([`71c734c`](https://github.com/OO-LD/oold-python/commit/71c734c6fb1864a6d9274efaf017be6032b2b4c6))

- **validation**: Enforce four more catalogued rules
  ([`fb99f5c`](https://github.com/OO-LD/oold-python/commit/fb99f5c3aebdec7227bd2cd68840b4cc2bd8c061))

- **validation**: Enforce narrow-only composition
  ([`13ade19`](https://github.com/OO-LD/oold-python/commit/13ade196c9ba8d6a9a9e8501e20ac213a688aaa6))

- **validation**: Enforce ten more normative rules
  ([`3030aa8`](https://github.com/OO-LD/oold-python/commit/3030aa879104dad3e52693f152505f58e240017f))

- **validation**: Enforce two more rules, and leave the third alone
  ([`bee7204`](https://github.com/OO-LD/oold-python/commit/bee7204df2b65240e9cf90add141c3eac8467968))

- **validation**: Gate checks on the catalogue, and add `oold checks`
  ([`f6fcbbb`](https://github.com/OO-LD/oold-python/commit/f6fcbbbdf9eaedfa755ac169b30a7cc5360c9ac6))

- **validation**: Model the rule catalogue and type the MCP results
  ([`5feef83`](https://github.com/OO-LD/oold-python/commit/5feef837cd70b787a9e7ac62bc9c2a005a556da5))

- **validation**: Track meta-schema v0.8.0
  ([`8e96921`](https://github.com/OO-LD/oold-python/commit/8e96921d72d05a8842348ce715004748ecdcc423))

- **validation**: Track the v1.0.0-rc.2 release
  ([`5a6b6d7`](https://github.com/OO-LD/oold-python/commit/5a6b6d77f9a98122328066ebb0abffcde219211b))

- **validation**: Track upstream's two-tier meta-schema split
  ([`09ede4a`](https://github.com/OO-LD/oold-python/commit/09ede4a0fca8fdfd2262ec532815011238afd6dd))

- **validation**: Vendor reshaped catalogue, and enforce its new rules
  ([`6589527`](https://github.com/OO-LD/oold-python/commit/6589527cc9791b76bf6fbebc43bc1c6fed25b7b5))

### Refactoring

- **validation**: Fold the check mappings into a single registry
  ([`57c1945`](https://github.com/OO-LD/oold-python/commit/57c1945c7819361d715ef10c6f541b3723fd485c))

### Testing

- **validation**: Arm remote-context fixture against literal @context
  ([`bd34c1b`](https://github.com/OO-LD/oold-python/commit/bd34c1b32de5b65ddc6e943b146388438d17aedc))

- **validation**: Give three checks a fixture that actually reaches them
  ([`793aaa1`](https://github.com/OO-LD/oold-python/commit/793aaa1b58d63a4aa0656813ad3e966df58688b1))


## v0.16.5 (2026-08-06)

### Bug Fixes

- **ci**: Send the pypi environment claim when publishing
  ([`3aa8029`](https://github.com/OO-LD/oold-python/commit/3aa8029eca14183b342991ed66b2cd5194d55942))


## v0.16.4 (2026-08-06)

### Bug Fixes

- Register a class only under the type IRIs it introduces
  ([`7ca1b85`](https://github.com/OO-LD/oold-python/commit/7ca1b85e37ed93ca2447ececfa11dc11a2265283))

### Chores

- License fix
  ([`daa8d8c`](https://github.com/OO-LD/oold-python/commit/daa8d8cfa325a3745c851c845b9fae7b5e51a0cc))

### Continuous Integration

- **release**: Add whats-changed notes with changelog link for zenodo
  ([`147d70f`](https://github.com/OO-LD/oold-python/commit/147d70fbf1c5da070f3cb9055fbe96e831fe8eaa))

- **release**: Update on title and authors
  ([`996c4de`](https://github.com/OO-LD/oold-python/commit/996c4dee6b4f07b6ec994e87cb341155a12e955c))


## v0.16.3 (2026-07-29)

### Bug Fixes

- Correct resolve_iri typo to resolve_iris in WikiDataSparqlResolver
  ([`d04108a`](https://github.com/OO-LD/oold-python/commit/d04108abb74387a1af1aea9db62e4eac1298a722))

- Restore tag-push release trigger; rewrite CONTRIBUTING for clarity and brevity
  ([`1b3436b`](https://github.com/OO-LD/oold-python/commit/1b3436b545b933520c8ea2cf7dc099635218ddce))

- **ci**: Disable uv cache in benchmark job to prevent post-step failure
  ([`c5873ed`](https://github.com/OO-LD/oold-python/commit/c5873edb6b3a39f43a5281a543cd62268e26b7f8))

- **ci**: Use git worktree for baseline benchmarks to avoid branch switch
  ([`5139d76`](https://github.com/OO-LD/oold-python/commit/5139d76e0f0a4a634d6426fe7a3edd94c86c99fd))

### Build System

- Map module names for optional UI extras to silence deptry warnings
  ([`d963a13`](https://github.com/OO-LD/oold-python/commit/d963a13265c07084782ffeb2cf9dcfb8bda228f3))

- Migrate from pyscaffold/setuptools to hatchling + uv tooling
  ([`9ce1f13`](https://github.com/OO-LD/oold-python/commit/9ce1f1335b9f408c837d88a54d92b65b0527e6b0))

### Chores

- Authorship for zenodo releases through CITATION.cff file; Guideline on contributing and docs
  updated with how to be author on zenodo
  ([`ff73bc0`](https://github.com/OO-LD/oold-python/commit/ff73bc063afcabd27aa3b564ddcce08d96640b5d))

- Ignore local files
  ([`bf1a9e0`](https://github.com/OO-LD/oold-python/commit/bf1a9e093d58a13436316eb6d09d3c73599a82e1))

- **release**: Seed version fields and changelog for psr
  ([`df5f4a8`](https://github.com/OO-LD/oold-python/commit/df5f4a8ae97ede104826df6f32fe9d8d1ee2a517))

### Continuous Integration

- Add conventional-commit commit-msg hook
  ([`d263194`](https://github.com/OO-LD/oold-python/commit/d263194ab0c428fdd27e88e680f75c61fe380472))

- Add semantic-release version preview on pull requests
  ([`75a2998`](https://github.com/OO-LD/oold-python/commit/75a29981387b91e3f8934fc515e6865367efcb22))

- Fix version-preview to show bump and changelog, v-prefixed and reworded
  ([`4db8800`](https://github.com/OO-LD/oold-python/commit/4db8800177b077610543dea1c7d3120ac8b31dfa))

- Make version-preview evaluate on main so PR bump shows correctly
  ([`92d4101`](https://github.com/OO-LD/oold-python/commit/92d410104d539236b4fc34bb7a5b02925ab98a81))

- **release**: Automate release on merge to main via psr
  ([`5ddafe7`](https://github.com/OO-LD/oold-python/commit/5ddafe7d850717acb4e353f406e4b592ab27add4))

- **release**: Configure python-semantic-release (psr) with static version
  ([`b81a511`](https://github.com/OO-LD/oold-python/commit/b81a511801ff25046b688f9a776ba1733aecdb04))

- **release**: Push release commit via github app token to satisfy branch ruleset
  ([`2e64068`](https://github.com/OO-LD/oold-python/commit/2e640683a819a0a4261ff2e635e15f09ae081284))

### Documentation

- Add landing hero on Home, move old content to new About page
  ([`32d22b5`](https://github.com/OO-LD/oold-python/commit/32d22b5041105f870546bae5021fb3eb5ad29b60))

- Add OO-LD logo, fix tab/icon rendering, uv-first install, tidy README
  ([`9404a1d`](https://github.com/OO-LD/oold-python/commit/9404a1d092e6eb8f354c12fd80e8891c3fe0b30e))

- Add tabs nav + logo + landing hero, fix page title, tidy README
  ([`e16d80c`](https://github.com/OO-LD/oold-python/commit/e16d80c73721b2fd972aa8bd75c919840a00106b))

- Drop redundant Development page (merged into Contributing)
  ([`6c929c2`](https://github.com/OO-LD/oold-python/commit/6c929c2fbf922e0b2d351b22197b7c549b7984eb))

- Fix + enlarge mermaid diagrams, hide footer on landing page
  ([`c87a92d`](https://github.com/OO-LD/oold-python/commit/c87a92ddd6fc93cc87e8abff15131ab0e930b7b7))

- Fix home hero right-side gap and top alignment
  ([`c6a9d0b`](https://github.com/OO-LD/oold-python/commit/c6a9d0bfcf1a9253281361f805032040b74b927e))

- Fix landing hero gradient — seamless yellow to bottom, no footer
  ([`b6cc144`](https://github.com/OO-LD/oold-python/commit/b6cc14436422e22f6a7c7fad92781fbb3de4927f))

- Fix raw tab artifacts (enable pymdownx.tabbed), lead with uv install
  ([`73ecc54`](https://github.com/OO-LD/oold-python/commit/73ecc54e15a87f7170c5abd1f8ac6a315a04e4c0))

- Reformat for markdownlint, add AI statement
  ([`50ffbed`](https://github.com/OO-LD/oold-python/commit/50ffbed8c1e7bbbe522e61d44e95dd714c7aad7b))

- Regenerate documentation and add citation support
  ([`d88f913`](https://github.com/OO-LD/oold-python/commit/d88f91382ba3ac4881ef0ddcee2056da69cbf238))

- Rm authors entirely to make use of auto contributor fetching from github (bots should be already
  ignored)
  ([`6446a91`](https://github.com/OO-LD/oold-python/commit/6446a919ed7700ad107bb1d99d0b8b78561026f1))

- Upd ai guidelines
  ([`bdfc192`](https://github.com/OO-LD/oold-python/commit/bdfc1925a354f0b1e20910e3b67274d498d46326))

- **contributing**: Document conventional commits and auto-release
  ([`cfaa811`](https://github.com/OO-LD/oold-python/commit/cfaa811a9b8529fc17ff8da2c164b7606891d617))
