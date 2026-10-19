from anvilbook import forever


def reagents(spell, *pairs):
    row = {'SpellID': spell}
    for i in range(8):
        item, count = pairs[i] if i < len(pairs) else ('0', '0')
        row[f'Reagent_{i}'], row[f'ReagentCount_{i}'] = item, count
    return row


def ability(spell, line='164', category='1', acquire='0', yellow='60', grey='100'):
    return {'Spell': spell, 'SkillLine': line, 'TradeSkillCategoryID': category, 'AcquireMethod': acquire,
            'TrivialSkillLineRankLow': yellow, 'TrivialSkillLineRankHigh': grey}


def creates(spell, item, amount='1'):
    return {'SpellID': spell, 'Effect': '24', 'EffectItemType': item, 'EffectBasePointsF': amount,
            'EffectTriggerSpell': '0'}


def item(item_id, name, skill='0', level='10', quality='1'):
    return {'ID': item_id, 'Display_lang': name, 'OverallQualityID': quality, 'ItemLevel': level,
            'RequiredLevel': '5', 'SellPrice': '20', 'RequiredSkillRank': skill}


TABLES = {
    'SkillLine': [{'ID': '164', 'DisplayName_lang': 'Blacksmithing'}, {'ID': '762', 'DisplayName_lang': 'Riding'}],
    'TradeSkillCategory': [{'ID': '1', 'Name_lang': 'Weapons'}, {'ID': '2', 'Name_lang': 'SEASON OF DISCOVERY'}],
    'SkillLineAbility': [
        ability('10'),                      # taught by pattern 300
        ability('11'),                      # trainer
        ability('12', acquire='1'),         # known when the profession is learned
        ability('15'),                      # taught by pattern 301 through learn spell 16
        ability('13', category='2'),        # Season of Discovery
        ability('17', category='0'),        # not a trade skill recipe
        ability('18', line='762'),          # not a profession
        ability('14'),                      # an enchant: makes no item
    ],
    'SpellEffect': [
        creates('10', '100', '2'), creates('11', '101'), creates('12', '102'), creates('13', '103'),
        creates('15', '105'), creates('17', '107'), creates('18', '108'),
        {'SpellID': '14', 'Effect': '53', 'EffectItemType': '0', 'EffectBasePointsF': '0', 'EffectTriggerSpell': '0'},
        {'SpellID': '16', 'Effect': '36', 'EffectItemType': '0', 'EffectBasePointsF': '0', 'EffectTriggerSpell': '15'},
    ],
    'SpellReagents': [reagents('10', ('200', '2'), ('201', '1')), reagents('11', ('200', '3'))],
    'ItemEffect': [{'ID': 'e1', 'TriggerType': '6', 'SpellID': '10'}, {'ID': 'e2', 'TriggerType': '6', 'SpellID': '16'},
                   {'ID': 'e3', 'TriggerType': '0', 'SpellID': '11'}],
    'ItemXItemEffect': [{'ItemID': '300', 'ItemEffectID': 'e1'}, {'ItemID': '301', 'ItemEffectID': 'e2'},
                        {'ItemID': '302', 'ItemEffectID': 'e3'}],
    # Pattern 301 has no row: the server sends its details itself.
    'ItemSparse': [item('100', 'Blade', level='20', quality='2'), item('101', 'Hilt'), item('102', 'Nail'),
                   item('105', 'Rivet'), item('200', 'Bar'), item('201', 'Flux'), item('300', 'Plans: Blade', '125')],
    'Item': [{'ID': '100', 'ClassID': '2'}, {'ID': '200', 'ClassID': '7'}],
}


def test_build_joins_the_recipes_of_offered_professions():
    table = forever.build(TABLES, '1.2.3')
    recipes = {r['spell']: r for r in table['recipes']}
    assert table['build'] == '1.2.3' and sorted(recipes) == [10, 11, 12, 15]
    assert recipes[10] == {'spell': 10, 'item': 100, 'profession': 'Blacksmithing', 'made': 2,
                           'reagents': [[200, 2], [201, 1]], 'yellow': 60, 'grey': 100,
                           'source': 'pattern', 'pattern': 300, 'learn': 125}
    assert (recipes[11]['source'], recipes[11]['learn'], recipes[11]['reagents']) == ('trainer', None, [[200, 3]])
    assert (recipes[12]['source'], recipes[12]['learn']) == ('start', 0)
    assert (recipes[15]['source'], recipes[15]['pattern'], recipes[15]['learn']) == ('pattern', 301, None)
    assert table['items'][100] == {'name': 'Blade', 'quality': 'Uncommon', 'itemLevel': 20, 'requiredLevel': 5,
                                   'sellPrice': 20, 'class': 'Weapon'}
    assert 'class' not in table['items'][200] and 301 not in table['items']


def test_the_written_table_reads_back():
    table = forever.build(TABLES, '1.2.3')
    path = forever.TABLE_PATH.parent / 'unused'
    assert forever.read(path) is None
    text = forever.dumps(table)
    assert text.count('\n') > len(table['recipes'])
    reread = forever.json.loads(text)
    assert reread['recipes'] == table['recipes']
    assert {int(i): d for i, d in reread['items'].items()} == table['items']


def test_apply_puts_forever_recipes_in_place_of_classic_ones():
    classic = {
        100: {'name': 'Classic Blade', 'icon': 'blade', 'vendorPrice': 0,
              'createdBy': [{'category': 'Blacksmithing', 'requiredSkill': 90, 'amount': [1, 1], 'reagents': []}]},
        101: {'name': 'Hilt', 'createdBy': [{'category': 'Blacksmithing', 'requiredSkill': 50, 'amount': [1, 1],
                                             'reagents': []}]},
        201: {'name': 'Flux', 'vendorPrice': 300},
        999: {'name': 'Gone', 'createdBy': [{'category': 'Blacksmithing', 'requiredSkill': 1, 'amount': [1, 1],
                                             'reagents': []}]},
    }
    out = forever.apply(classic, forever.build(TABLES, '1.2.3'))
    blade = out[100]
    assert (blade['name'], blade['icon'], blade['quality']) == ('Blade', 'blade', 'Uncommon')
    assert blade['createdBy'] == [{'amount': [2, 2], 'requiredSkill': 125, 'category': 'Blacksmithing',
                                   'reagents': [{'itemId': 200, 'amount': 2}, {'itemId': 201, 'amount': 1}],
                                   'yellow': 60, 'grey': 100, 'source': 'pattern', 'estimated': False,
                                   'pattern': 300}]
    # A trainer recipe keeps its classic learn skill; one without a classic recipe takes yellow.
    assert (out[101]['createdBy'][0]['requiredSkill'], out[101]['createdBy'][0]['estimated']) == (50, True)
    assert (out[105]['createdBy'][0]['requiredSkill'], out[105]['createdBy'][0]['estimated']) == (60, True)
    assert out[102]['createdBy'][0]['requiredSkill'] == 0
    assert out[999]['createdBy'] == [] and out[201]['vendorPrice'] == 300
    assert classic[100]['name'] == 'Classic Blade' and len(classic[999]['createdBy']) == 1
    assert forever.apply(classic, None) is classic


def test_the_shipped_table_is_forever():
    table = forever.read(forever.TABLE_PATH)
    assert table is not None and table['build'].startswith('1.60.')
    professions = {r['profession'] for r in table['recipes']}
    assert professions == {'Alchemy', 'Blacksmithing', 'Cooking', 'Enchanting', 'Engineering', 'First Aid',
                           'Leatherworking', 'Mining', 'Poisons', 'Tailoring'}
    by_item = {r['item']: r for r in table['recipes']}
    # Rock Garden exists only on Forever; Forever lowered the Deadly Bronze Poniard pattern to 100.
    assert (by_item[279948]['source'], by_item[279948]['learn']) == ('pattern', 140)
    assert (by_item[3490]['pattern'], by_item[3490]['learn']) == (2883, 100)
    assert table['items'][279948]['name'] == 'Rock Garden'
