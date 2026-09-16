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
    ): 'aea265f5dff7845e93f2061c80b223e8c000546cb04796b0a606c7cca94e9572',
    (
        'etape',
        'caisse',
    ): '0adf27ead5e61abe5d425b91e36a8c8ecb9c0680189f0d26a1db43070572a698',
    (
        'etape',
        'choix_venture',
    ): '1ac8e9123da0a7eea8525db275d4c89c182bcd65d5e11018a56fc6af3ae222b1',
    (
        'etape',
        'collect_feedback',
    ): '62082837c55d88fac881babd59685911c70a3d8fd4720875e96d37198a75d4f4',
    (
        'etape',
        'conception_poc',
    ): 'f65577eb256f4052312efe49078fc6f61b6cb17ba9a23cdbcc0aa9275de76caa',
    (
        'etape',
        'pre_prospection',
    ): 'bae65a3ef58f5735bc88c17d50b88128d91e1e6de5a292b17a9d88b19e49b0ee',
    (
        'etape',
        'prospection_light',
    ): '226321cac33aeb5b60b517b0435984ed165352c97eb84377f890250546f850a2',
    (
        'etape',
        'prospection_lourde',
    ): 'd4ac16a9402b842ede2075632755bf4d5a0860cec6c6433cc5ff52dbcb016e35',
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
    (
        'lien',
        'pre-poc',
    ): '40f272829674ebc13a0e2a9001f6765b8396b4178b6dc159028fb691e5c0b1df',
    (
        'llm',
        'build_artifact',
    ): '86c37da48e06fdeda79967546a83e8b7269832820517e009fc2f0eb160a67e11',
    (
        'llm',
        'classify_owner_intent',
    ): 'd0c036b0e127cebcd01fcf1dc3db152d71d6fe5c9d4ef8a5d0d5a4fdb2b477f3',
    (
        'llm',
        'classify_reply',
    ): 'ef871cf1b9c603444060ef2bd5dc6bc43029eeabd97906ee371ec2e96bd85db9',
    (
        'llm',
        'cluster_demand',
    ): '6d22e9f9cb983faaf7c46a19c592fb316bb21a458de410fcfbbee3e263206551',
    (
        'llm',
        'consolidate',
    ): 'a80614644339d728dc5e016c993b40842409fafd6e69baa4b13ff8a814ad6b89',
    (
        'llm',
        'draft_hypothesis_full',
    ): '7778f04c41610f260301d8cfcfa5ccb36631751c3e6e0e5944f46ddb79b828a6',
    (
        'llm',
        'draft_hypothesis_smoke',
    ): '7778f04c41610f260301d8cfcfa5ccb36631751c3e6e0e5944f46ddb79b828a6',
    (
        'llm',
        'draft_price',
    ): 'a1a6081fca51dcca241bbf4596784369f5a22e55ffd150cbf974529666405c82',
    (
        'llm',
        'edit_serge_md',
    ): 'a80614644339d728dc5e016c993b40842409fafd6e69baa4b13ff8a814ad6b89',
    (
        'llm',
        'extract_meeting',
    ): 'faa07a11e3f00665262947c65d61983de4d7336004b556f33172c67a69dafb3f',
    (
        'llm',
        'fill_slots',
    ): 'e19913111dcfbd738ea0334e1daaefd8300668561a2feb2c19c7c5d9dafa8716',
    (
        'llm',
        'install_guide',
    ): '30ec66e905b9a0da3cfba2fc099712f23599a6cc3c3a9f43f1d57dd37387aedf',
    (
        'llm',
        'judge_allocator',
    ): '77dce1ed55710205fad82a177ad1ed039c6610ec0f7f6e974404c1c60fb1b377',
    (
        'llm',
        'judge_consequence',
    ): 'd0c036b0e127cebcd01fcf1dc3db152d71d6fe5c9d4ef8a5d0d5a4fdb2b477f3',
    (
        'llm',
        'options_pivot',
    ): '62a66c99194df80ce1393845485215b4f6782aeb1f577f18a90e4df27d11e44a',
    (
        'llm',
        'plan_scale',
    ): '62a66c99194df80ce1393845485215b4f6782aeb1f577f18a90e4df27d11e44a',
    (
        'llm',
        'qualify_prospect',
    ): 'aef3956ef13b48d3d27ac70620bcb561e28029c4bd7433e8947b6135dc645036',
    (
        'llm',
        'render_context_fr',
    ): 'd0c036b0e127cebcd01fcf1dc3db152d71d6fe5c9d4ef8a5d0d5a4fdb2b477f3',
    (
        'llm',
        'reply_intent',
    ): '9bb67e21ca9f70becae5e596e30ae841b04759ee36893eecb34729286f7cab38',
    (
        'llm',
        'resume_test',
    ): '62a66c99194df80ce1393845485215b4f6782aeb1f577f18a90e4df27d11e44a',
    (
        'llm',
        'review_build',
    ): 'd78d931cde1b175ab9086f10ad76ed9065cfe47ff142de56618a561f86ac0189',
    (
        'llm',
        'review_other',
    ): 'c37ae9d80a0aff7866a418ad3af54a41e0056f994c0fdf1d85df9d4102c1f29a',
    (
        'llm',
        'score_call',
    ): '8c41ee0888d6a38aaaa27303fda5db4062020f36e4b4ce84e711818b95384436',
    (
        'llm',
        'score_lead_departage',
    ): 'aef3956ef13b48d3d27ac70620bcb561e28029c4bd7433e8947b6135dc645036',
    (
        'llm',
        'summarize_build_debt',
    ): 'd78d931cde1b175ab9086f10ad76ed9065cfe47ff142de56618a561f86ac0189',
    (
        'llm',
        'summarize_thread',
    ): '8c41ee0888d6a38aaaa27303fda5db4062020f36e4b4ce84e711818b95384436',
    (
        'llm',
        'voice_dialog',
    ): 'ba5a234323c142994a89196718be564502eeeaf4528a347efead8276572bf88f',
    (
        'llm',
        'voice_script',
    ): '448c729bd347697b3757387b0fde8f67cb5b96d6b76aa79889387d5276d4f115',
    (
        'llm',
        'write_followup',
    ): 'e19913111dcfbd738ea0334e1daaefd8300668561a2feb2c19c7c5d9dafa8716',
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
    ): '14bc00395e804c0ac6d02c8e0271673df4909b0ba7f2bfef66fd2c8ce723b067',
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
        'navigateur',
    ): 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
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
