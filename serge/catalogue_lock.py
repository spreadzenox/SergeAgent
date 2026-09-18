#!/usr/bin/env python3
"""SHA figés du catalogue (fichiers + sous-objets). Maj = test rouge sinon."""

from __future__ import annotations

# (kind, id) → files_sha. Contenu des fichiers seulement, puis compose.
SHA_ATTENDUS: dict[tuple[str, str], str] = {
    (
        'canal',
        'email',
    ): 'cc757e2fd186880b8c39b6c84e8819a62e79ac257c87dabdfa687a95965b291f',
    (
        'canal',
        'voice',
    ): 'cdfc6e7351890d553232d2b571d503b5cab4d7c4929076c94448556a66e2f367',
    (
        'etape',
        'build_venture',
    ): '8296fa4283fa2386b4a50891646b074e1a029e0c40d3a5e86d9da75fb287ddac',
    (
        'etape',
        'caisse',
    ): '52c4c17ca9b5cded964ddd82d6340eb956fe4e7c356203cc83d2d60ee3732fa0',
    (
        'etape',
        'choix_venture',
    ): 'a8508bd04c81eee001e0e7c3c4bc7da481f09fb3aba3fa36fc31bc72e96f1bf7',
    (
        'etape',
        'collect_feedback',
    ): '490e674a742ae35c167d21cfb928ef0a7704310a8ab148f0517592582a20a9e1',
    (
        'etape',
        'conception_poc',
    ): 'd88d17faa50488b1f344f03c89e3f914c40330eb1483057625a99bc4885931f9',
    (
        'etape',
        'pre_prospection',
    ): 'f29a260ec24b7857cadbebf2428791f31d64ea8cd4ad13e041a502855dd51695',
    (
        'etape',
        'prospection_light',
    ): '81a9647f9f581f2acd54b10e76904450768e618bd4f697c6590142bd19fc7c4a',
    (
        'etape',
        'prospection_lourde',
    ): '44e5958e609b14c46f445b6965f4bacca4874b32d75f95af34a628de5becbd0f',
    (
        'lien',
        'build-lourde',
    ): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    (
        'lien',
        'choix-build',
    ): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    (
        'lien',
        'light-choix',
    ): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    (
        'lien',
        'lourde-caisse',
    ): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    (
        'lien',
        'lourde-feedback',
    ): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    (
        'lien',
        'poc-light',
    ): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    ('lien', 'pre-poc'): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    ('llm', 'build_artifact'): 'a8b458813711a567660299b8aaa1c434079dfcf217340727a31545e716593209',
    ('llm', 'classify_owner_intent'): '61f425e723f5466814d8fec08810d19667ec90985cec536c7b7de9506c17bb85',
    ('llm', 'classify_reply'): '41640585fba6e127bdd0d8f8af3a4c0b9bcef9941a44d410f8f7c7d99824b867',
    ('llm', 'cluster_demand'): 'e7074b97eb3ce50220c913b59308613147c864ed3c6a3e4687998bb440a69b1e',
    ('llm', 'listen_choose_poc'): 'd20ac17b69f69686d86d55cdefd6cc8d62813804c7959bc5cd1eba1dba786b7b',
    ('llm', 'listen_discover_needs_a'): 'b75ac17c2b769cdcfce88de82492a05c40cb30b836ddd162dcb12322a65fa664',
    ('llm', 'listen_discover_needs_b'): 'b75ac17c2b769cdcfce88de82492a05c40cb30b836ddd162dcb12322a65fa664',
    ('llm', 'consolidate'): '51ba6ee8b1d9c31641b38cd9adc0423f32eab351c25a8a1bcedf2dfa67a6216f',
    (
        'llm',
        'draft_hypothesis_full',
    ): '12dcfb0e6991fc525879d3246bf9d314c9754ec598d775163b47e456719f5ab5',
    (
        'llm',
        'draft_hypothesis_smoke',
    ): '12dcfb0e6991fc525879d3246bf9d314c9754ec598d775163b47e456719f5ab5',
    (
        'llm',
        'draft_price',
    ): 'a0d6aca043e34aa9697c4462b8d840c22922891456c457c6abf1dca29e6f32a4',
    (
        'llm',
        'edit_serge_md',
    ): '51ba6ee8b1d9c31641b38cd9adc0423f32eab351c25a8a1bcedf2dfa67a6216f',
    (
        'llm',
        'extract_meeting',
    ): 'bc7764f49f6ceded3c3236a5af2ade1eced4e2aeb71d45be1b218436f2345aa2',
    (
        'llm',
        'fill_slots',
    ): '30db35982ba79c2ec9c6e0f3453f953541266238dc0d66c637ba42c32f031e9f',
    (
        'llm',
        'install_guide',
    ): '576c386b0d4d41acef99edd176e6bd136092196319e588a13eb220ab93e1b3dc',
    (
        'llm',
        'judge_allocator',
    ): '81452269e96caa48f5a2e260506d3b46beb13786b5fbb54d34daf4d34c48461c',
    (
        'llm',
        'judge_consequence',
    ): '61f425e723f5466814d8fec08810d19667ec90985cec536c7b7de9506c17bb85',
    (
        'llm',
        'options_pivot',
    ): '3a10cbadc5287010dd7418cc7c1cbb32f77464c7b4f5fa6ad896692d0f86481f',
    (
        'llm',
        'plan_scale',
    ): '3a10cbadc5287010dd7418cc7c1cbb32f77464c7b4f5fa6ad896692d0f86481f',
    (
        'llm',
        'qualify_prospect',
    ): '545b4294389f12ee364e5c13c398dda56448e556b086f2c1c946f187467c6b4d',
    (
        'llm',
        'render_context_fr',
    ): '61f425e723f5466814d8fec08810d19667ec90985cec536c7b7de9506c17bb85',
    (
        'llm',
        'reply_intent',
    ): '2b38fc112604e0a6908747f96e5aa1f05658dfb31b6b38f04b087f893dcabce6',
    (
        'llm',
        'resume_test',
    ): '3a10cbadc5287010dd7418cc7c1cbb32f77464c7b4f5fa6ad896692d0f86481f',
    (
        'llm',
        'review_build',
    ): '66357297ddf3dd3548bd37fd9e51db37ed435163b31ff0e1f41bc138250484df',
    (
        'llm',
        'review_other',
    ): 'd799a53ba2dcdbd9bf6a6878230b90cf2071da9215a09a9fc940a140b050c8d3',
    (
        'llm',
        'score_call',
    ): 'c4eea03e106d0f419aae4f4f5fb567acd165e72fa73db149692ad200c19a7936',
    (
        'llm',
        'score_lead_departage',
    ): '545b4294389f12ee364e5c13c398dda56448e556b086f2c1c946f187467c6b4d',
    (
        'llm',
        'summarize_build_debt',
    ): '66357297ddf3dd3548bd37fd9e51db37ed435163b31ff0e1f41bc138250484df',
    (
        'llm',
        'summarize_thread',
    ): 'c4eea03e106d0f419aae4f4f5fb567acd165e72fa73db149692ad200c19a7936',
    (
        'llm',
        'voice_dialog',
    ): '3b8aae5f41f3f1863d75d3352e23b919f9e52b08d5e607f1864dbb2c1904a2d3',
    (
        'llm',
        'voice_script',
    ): '60db5b252876481d93542ef1dea76a6075001b81c18486af7aea4219ac403885',
    (
        'llm',
        'write_followup',
    ): '30db35982ba79c2ec9c6e0f3453f953541266238dc0d66c637ba42c32f031e9f',
    (
        'outil',
        'agenda',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    (
        'outil',
        'boite_serge',
    ): 'bd23fbd3b6e0f612a913404e37b7def202b8a09fdda3cf21a25c325dfc10c6b7',
    (
        'outil',
        'catalogue',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    (
        'outil',
        'demande_capacite',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    (
        'outil',
        'fiches',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    (
        'outil',
        'identity_advanced',
    ): '5d695c4535a4dde940832f596d24fb5cf0f668850132efc42dd574e0212bef1b',
    (
        'outil',
        'identity_basique',
    ): '5d695c4535a4dde940832f596d24fb5cf0f668850132efc42dd574e0212bef1b',
    (
        'outil',
        'memory_search',
    ): 'c28e81cd9475e25fcd2daaf0a0951ab7b456de38e9e8269138a1c26d090df730',
    (
        'outil',
        'db_read',
    ): 'b982c1b16e025fee5310fcaa2b701b22a58a56d5c0bb134566b24f4425bfab18',
    (
        'outil',
        'navigateur',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    (
        'outil',
        'web_search',
    ): '51813343a03a41da95acc479d1eaad4b91c9d7da9ce5806fbe9cd31584d59d43',
    (
        'tech',
        'cluster_listen',
    ): '99b2b8c8a2d6ceed88bc54a1503d27f4c71034dc7d55f9fa61d5e83b121a5796',
    (
        'tech',
        'dunning',
    ): '4ea7b789a55ec926c14423a65cbe9305e9a2d4be500a7664d5a6f9ac8fe6cf74',
    (
        'tech',
        'guards_check',
    ): 'fc1d5a258cb349af3ac3cbdb65ca33971efdf29c6aabf665793a3b81da0654bf',
    (
        'tech',
        'listen_collect',
    ): 'c21b86c84da79cfe07c4c741e01373e80dc4afabf45825e23e2e025265648687',
    (
        'tech',
        'memory_fts_index',
    ): 'c28e81cd9475e25fcd2daaf0a0951ab7b456de38e9e8269138a1c26d090df730',
    (
        'tech',
        'metrics_u',
    ): 'eaea16e8748b7f837629da53a86ca8d6bf51df59dd761bf42cf4f74a40060ba6',
    (
        'tech',
        'select_pre_venture',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    (
        'tech',
        'sequencer',
    ): '9eb5732066a8df38fb130be9a57cc4670696298061e650bc2f042fe328247cae',
    (
        'tech',
        'stripe_receive',
    ): '8d832135d052475f4b24de6c22e1678be8ae8e7786cdd1c19a2811a4b85e586f',
}
