# CHANGELOG

All notable changes to this project are documented here. Versions are cut
automatically from Conventional Commits on every merge to main by
[python-semantic-release](https://python-semantic-release.readthedocs.io/). Do
not edit released sections by hand.

<!-- version list -->

## v1.0.0 (2026-09-15)

### Bug Fixes

- Aliases, default_factory and registration in the notation module
  ([`4eda165`](https://github.com/OO-LD/oold-python/commit/4eda16566213170fc15324dc80326607cbff17bb))

- Equality no longer depends on whether a link was resolved
  ([`baea692`](https://github.com/OO-LD/oold-python/commit/baea692cee047d9909eb83ab7056ab84d78dc114))

- Link annotations no longer force a None arm on every dereference
  ([`09d1c18`](https://github.com/OO-LD/oold-python/commit/09d1c188f0bf011701140b57b21e032f94cde3c8))

- Preserve declared default IRIs and repair link serialisation
  ([`fac1ef7`](https://github.com/OO-LD/oold-python/commit/fac1ef71a3d553059dcb0a6ae99d59b5db6faca6))

- Reach the annotate function through annotationlib
  ([`3f36c92`](https://github.com/OO-LD/oold-python/commit/3f36c92855671f02524e7d865a764ec1f080b3ae))

- Read class annotations under PEP 649 deferred evaluation
  ([`cbc1c98`](https://github.com/OO-LD/oold-python/commit/cbc1c985528e061e7b0bbe959fe1c134daefc2ca))

- Restore legacy behaviour the descriptor binding did not reproduce
  ([`6fb1076`](https://github.com/OO-LD/oold-python/commit/6fb10768d2258600f32d07a86bbf4df3fe94ee33))

- Shared Field reuse, Annotated defaults, equality and type arrays
  ([`38d81b0`](https://github.com/OO-LD/oold-python/commit/38d81b05744c96a40cf954afdfdcacc744285f1a))

- Stop resolution failures being hidden, and link mutations being lost
  ([`91e136f`](https://github.com/OO-LD/oold-python/commit/91e136f57597fa496227435c673ccc77ae4f7b8b))

- Support generated-package declaration shapes in the descriptor binding
  ([`d8dbac9`](https://github.com/OO-LD/oold-python/commit/d8dbac9ca0a5b14c26ba58c23fba040d83e7e93f))

- **examples**: Benchmark the legacy binding, not the new one twice
  ([`1e5721c`](https://github.com/OO-LD/oold-python/commit/1e5721ceb64aef5a12cb32829bd6a22f8948e009))

- **examples**: Make wiki_data.py run against the live endpoint
  ([`8a668a4`](https://github.com/OO-LD/oold-python/commit/8a668a4cd07ba99b73c63b2f07828454c4651cb8))

- **examples**: Read name from rdfs:label, not the Commons category
  ([`14a8fd5`](https://github.com/OO-LD/oold-python/commit/14a8fd59e5d94b8549966ae6d957598bb01604db))

- **experimental**: Lossless de-serialisation of union link arms
  ([`ce8eb21`](https://github.com/OO-LD/oold-python/commit/ce8eb217d4f82db57420b770523b57917cbcfc2c))

- **typing**: Make the binding swap visible to a type checker
  ([`80e8e99`](https://github.com/OO-LD/oold-python/commit/80e8e99c4246ec7f94566e2b1bf3ccb6ffb5adaf))

- **v1**: Encode non-JSON types in to_json
  ([`d96476c`](https://github.com/OO-LD/oold-python/commit/d96476cbf6139a38c2e44cb301da2a2f83cf3413))

- **v1**: Register full class IRI set and share the type registry
  ([`9cb6f5f`](https://github.com/OO-LD/oold-python/commit/9cb6f5f9672fda0c85385bf5e3d9460c99895e50))

### Chores

- Ignore .vscode, node_modules and .claude
  ([`221d88d`](https://github.com/OO-LD/oold-python/commit/221d88d3bfdcf8af746acfd128be171a7e5f9d71))

- Tell deptry annotationlib is stdlib from 3.14
  ([`2458473`](https://github.com/OO-LD/oold-python/commit/24584736e3b56ea3c14435ad608f4f5c8be0c335))

### Documentation

- Correct stale claims and tabulate notation support
  ([`0abd4c4`](https://github.com/OO-LD/oold-python/commit/0abd4c43ea4f14039fd098e3aaff338cd8bf8047))

- Name the recommended link notation, and mirror the v1 binding swap
  ([`df13e87`](https://github.com/OO-LD/oold-python/commit/df13e87c44cc978ba4486160df2c640b09faaa90))

- Record the downstream verification results
  ([`100f694`](https://github.com/OO-LD/oold-python/commit/100f6949898d7c7fb09815835475e0f45a4ca90c))

- Record the metaclass identity requirement for the replacement
  ([`c7af84c`](https://github.com/OO-LD/oold-python/commit/c7af84c6d289f507d320d5858577f41d437b50d4))

- **validation**: Correct how pyld actually fails on each count
  ([#150](https://github.com/OO-LD/oold-python/pull/150),
  [`4556612`](https://github.com/OO-LD/oold-python/commit/455661251a7ca5681608a0c2391dd77ae0e33775))

- **validation**: Document the fault status in the how-to
  ([#152](https://github.com/OO-LD/oold-python/pull/152),
  [`6b31fd3`](https://github.com/OO-LD/oold-python/commit/6b31fd37af1c9c97b9a4aecb5d3583f9aa30ccf6))

- **validation**: Give the context walker a true justification
  ([#150](https://github.com/OO-LD/oold-python/pull/150),
  [`4556612`](https://github.com/OO-LD/oold-python/commit/455661251a7ca5681608a0c2391dd77ae0e33775))

- **validation**: State what --offline pins and what nothing pins
  ([#149](https://github.com/OO-LD/oold-python/pull/149),
  [`abcad76`](https://github.com/OO-LD/oold-python/commit/abcad7665a235169eab7465e16f36b4aefda92e4))

### Features

- Carry the typed query subscription into the descriptor binding
  ([`5774fcd`](https://github.com/OO-LD/oold-python/commit/5774fcd49964302fee5b36c8aa7dbfe0a09a6c37))

- Declare link optionality in the type parameter
  ([`cc8470d`](https://github.com/OO-LD/oold-python/commit/cc8470d6aabfd1ce5baa871a2b35b00c8088df98))

- Derive x-oold-range from the link annotation
  ([`d66f037`](https://github.com/OO-LD/oold-python/commit/d66f037eb6dc20763935486d5399e02f3ab40de2))

- Extend the binding switch to pydantic v1
  ([`15ab140`](https://github.com/OO-LD/oold-python/commit/15ab140855404d0931f1a500799841ca2b8c0388))

- Make the descriptor binding the default
  ([`3a4a98a`](https://github.com/OO-LD/oold-python/commit/3a4a98a2bfa25a1df7776ed96e03777292190d5f))

- Make the descriptor binding the default and drop AutoLinkedModel
  ([`57389a3`](https://github.com/OO-LD/oold-python/commit/57389a33fdf97df924273eb34677c6813cc2b4a0))

- OOLD_LINKS=0 runs models as plain pydantic
  ([`042d9a2`](https://github.com/OO-LD/oold-python/commit/042d9a2cb9f5c1fac953866e2fe05bb52021fd10))

- OoldField(required=True) carries link requiredness
  ([`b20175a`](https://github.com/OO-LD/oold-python/commit/b20175a03a0e1136da9ecd7d5a168c7e337ae58a))

- Opt-in descriptor binding via OOLD_DESCRIPTOR_BINDING
  ([`67ac41b`](https://github.com/OO-LD/oold-python/commit/67ac41b63e00618330436324005b2ad6700f85cf))

- Public type registry API
  ([`5f97f94`](https://github.com/OO-LD/oold-python/commit/5f97f94a6bb5e37f431559e01a0fff6856d1e877))

- Raise mandatory-link failures on access, and translate the DSL to SPARQL
  ([`b126971`](https://github.com/OO-LD/oold-python/commit/b126971e0ceb732d7259712f67631ab57f55b28a))

- Type link fields in both directions via Link[T] / LinkList[T]
  ([`b33b5a7`](https://github.com/OO-LD/oold-python/commit/b33b5a79633b603b3ecc396e007632c6e21e698c))

- **experimental**: Downstream API parity layer for the descriptor binding
  ([`a96a91b`](https://github.com/OO-LD/oold-python/commit/a96a91bfd2c2811ecbadbe385782a62b45f3c159))

- **experimental**: Graph-object binding prototypes and benchmarks
  ([`e55c64f`](https://github.com/OO-LD/oold-python/commit/e55c64fbb1b46765e3ca3e28eb1e7777b59d7f31))

- **experimental**: OoldField() without arguments infers the link target
  ([`b2c62e5`](https://github.com/OO-LD/oold-python/commit/b2c62e5996de18f1568fbebd853d6841303f2b51))

- **experimental**: Pydantic v1 descriptor binding
  ([`c41ee9c`](https://github.com/OO-LD/oold-python/commit/c41ee9cca2aaf34f878374f548e38a919877f8e9))

- **experimental**: Share the type registry with oold.model._types
  ([`d5a5d64`](https://github.com/OO-LD/oold-python/commit/d5a5d64a19859d6082b2691ac64acea12c4181b7))

### Refactoring

- One link descriptor and one construction guard for both versions
  ([`16ffdb2`](https://github.com/OO-LD/oold-python/commit/16ffdb22c47b5b8ebe889124c914a651adc34a4a))

- Promote the descriptor binding out of experimental
  ([`562419a`](https://github.com/OO-LD/oold-python/commit/562419aa179b6b24f92f346f3e50a368a43f4587))

- Remove dead code and the duplication behind it
  ([`93f18a1`](https://github.com/OO-LD/oold-python/commit/93f18a14e4554636fd617d298705bca2f6f96d46))

- Share the downstream API surface between v1 and v2
  ([`66b3292`](https://github.com/OO-LD/oold-python/commit/66b329290a2e6b63bbdde9ecf22c78626baad8b4))

### Testing

- **validation**: Check context equality over every schema, not thirteen
  ([#153](https://github.com/OO-LD/oold-python/pull/153),
  [`d47f39e`](https://github.com/OO-LD/oold-python/commit/d47f39e95a748531f15eca4b3bbf1de9159bff7d))

- **validation**: Pin the pyld equivalence the docstring argues from
  ([#150](https://github.com/OO-LD/oold-python/pull/150),
  [`4556612`](https://github.com/OO-LD/oold-python/commit/455661251a7ca5681608a0c2391dd77ae0e33775))


## v0.20.0 (2026-09-11)

### Features

- **validation**: Report an unexpected exception as a validator fault
  ([#151](https://github.com/OO-LD/oold-python/pull/151),
  [`70e0102`](https://github.com/OO-LD/oold-python/commit/70e0102df18a9239fac1407d0acb701c0293ef21))

### Testing

- **validation**: Cover genuine remote retrieval and the warm cache
  ([#139](https://github.com/OO-LD/oold-python/pull/139),
  [`7fd050f`](https://github.com/OO-LD/oold-python/commit/7fd050f513dafe715d5fe6dfae6bdf0e1db788a8))

- **validation**: Cover the fault paths the guard-shaped tests missed
  ([#151](https://github.com/OO-LD/oold-python/pull/151),
  [`70e0102`](https://github.com/OO-LD/oold-python/commit/70e0102df18a9239fac1407d0acb701c0293ef21))


## v0.19.0 (2026-08-31)

### Features

- **validation**: Add oold meta vendor command
  ([#146](https://github.com/OO-LD/oold-python/pull/146),
  [`f714002`](https://github.com/OO-LD/oold-python/commit/f71400241ec08cdaab53dce5570c0341865b9fab))

### Testing

- **validation**: Cover @vocab suppressing the coverage finding
  ([#137](https://github.com/OO-LD/oold-python/pull/137),
  [`9f7d12a`](https://github.com/OO-LD/oold-python/commit/9f7d12a4b4a94ada35f9c8319071390ef026499a))


## v0.18.4 (2026-08-31)

### Bug Fixes

- **validation**: Narrow roundtrip.py's broad exception handling
  ([#147](https://github.com/OO-LD/oold-python/pull/147),
  [`354d966`](https://github.com/OO-LD/oold-python/commit/354d96627239f61c28463009078bdc3f6c242907))

- **validation**: Use jsonschema[format-nongpl] for format checks
  ([#140](https://github.com/OO-LD/oold-python/pull/140),
  [`03336e3`](https://github.com/OO-LD/oold-python/commit/03336e3c9aba009f725a424fa3371d89f94d038d))

### Testing

- **parity**: Compare against oold-js instead of oold-schema's scripts
  ([#144](https://github.com/OO-LD/oold-python/pull/144),
  [`42d0d74`](https://github.com/OO-LD/oold-python/commit/42d0d740fec4285ca6c3b9bd9c0c028a9368b601))


## v0.18.3 (2026-08-29)

### Bug Fixes

- **validation**: Revalidate the remote meta cache instead of trusting it
  ([#143](https://github.com/OO-LD/oold-python/pull/143),
  [`8e83643`](https://github.com/OO-LD/oold-python/commit/8e83643a557d7a133b80632b45649cb6d7632b52))

### Testing

- **validation**: Cover the conditional-fetch helper directly
  ([#143](https://github.com/OO-LD/oold-python/pull/143),
  [`8e83643`](https://github.com/OO-LD/oold-python/commit/8e83643a557d7a133b80632b45649cb6d7632b52))


## v0.18.2 (2026-08-29)

### Bug Fixes

- **validation**: Treat an absent @context as every property unmapped
  ([#142](https://github.com/OO-LD/oold-python/pull/142),
  [`bc6e1c9`](https://github.com/OO-LD/oold-python/commit/bc6e1c98bd98bf97431afed767ca5f33bd3ea985))


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
