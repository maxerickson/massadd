import argparse
import re
import xml.etree.ElementTree as ElementTree

def tsvquote(text):
    if text is not None and '"' in text:
        text=text.replace('"','""')
        return '"{}"'.format(text)
    else:
        return text

prefixes={
    "E.":"East",
    "N":"North",
    "N.":"North",
    "No.":"North",
    "S":"South",
    "S.":"South",
    "So.":"South",
    "Mt":"Mount",
    "Mt.":"Mount",
    "W.":"West",
    "Rt.":"Route",
    "Sgt":"Sergeant",
    "Sgt.":"Sergeant",
    "St":"Saint",
    "Mass.":"Massachusetts"
}

suffixes={"Ave":"Avenue",
    "Blvd":"Boulevard",
    "Dr":"Drive",
    "Hwy":"Highway",
    "Ln":"Lane",
    "Pk":"Park",
    "Pkwy":"Parkway",
    "Rd":"Road",
    "Sq":"Square",
    "St":"Street",
    "St. N":"Street North"}

def expand_street(street):
    # simple normalizations
    if street.isupper():
        street=street.title()
    if street.endswith("."):
        street=street[:-1]
    # replace certain prefixes.
    for key in prefixes.keys():
        if street.startswith(key+" "):
            street=prefixes[key]+" "+street[len(key)+1:]
    # replace abbreviations at end of street
    for key in suffixes.keys():
        if street.endswith(key):
            street=street[:-len(key)]+suffixes[key]
    return street

def find_housenumber(address):
    if address[0].isnumeric():
        idx=0
        hnumber=''
        while address[idx].isnumeric() or address[idx]=="-":
            hnumber+=address[idx]
            idx+=1
        while address[idx] in " .,":
            idx+=1
        rest=address[idx:]
    else:
        hnumber=None
        rest=address
    return hnumber,rest

def find_zipcode(address):
    if address[-1].isnumeric():
        idx=-1
        zip=""
        while address[idx].isnumeric() or address[idx]=="-":
            zip=address[idx]+zip
            idx-=1
        while address[idx] in " .,":
            idx-=1
        rest=address[:idx+1]
    else:
        zip=None
        rest=address
    if zip=="00":
        zip=None
    return zip,rest

def find_state(address):
    if address.endswith("MA"):
        idx=-3
        while address[idx] in " .,":
            idx-=1
        rest=address[:idx+1]
        state="MA"
    else:
        rest=address
        state=None
    return state,rest

def find_pobox(address):
    po=re.search(" ?P.{0,2}O.{0,2}box (\w*)",address, re.I)
    if po is not None:
        start=po.start()
        end=po.end()
        rest=address[:start]+address[end:]
        idx=0
        while rest[idx] in " -.,":
            idx+=1
        return po.group(1),rest[idx:]
    else:
        return None,address

def parse_full(address):
    if address[0].isnumeric():
        hnumber, street=address.split(" ",1)
    else:
        hnumber=None
        street=address
    return hnumber,street

dump2=open("dump2.txt", "w")

def parse_ma(address):
    address=address.strip()
    pobox,address=find_pobox(address)
    hnumber, address=find_housenumber(address)
    zip, address=find_zipcode(address)
    state,address=find_state(address)
    dump2.write(address+"\n")
    items=dict()
    try:
        if address.count(',')==0:
            street=address
            city=None
        if address.count(',')==1:
            street, city=address.split(",")
        #~ else:
            #~ print(address)
        # store None for string.format
        items["addr:housenumber"]=hnumber
        if street is not None:
            street=street.strip()
        items["addr:street"]=expand_street(street)
        if city is not None:
            city=city.strip()
            if city.isupper():
                city=city.title()
        if city=="Manchester-by-the-S":
            city="Manchester by the Sea"
        items["addr:city"]=city
        items["contact:pobox"]=pobox
        items["addr:state"]=state
        items["addr:postcode"]=zip
    except:
        print("ERROR IN PARSER",address)
        raise
    return items


def alter_osm(infile, outfile):
    # modify xml data with split address tags.
    tree=ElementTree.parse(infile)
    osm=tree.getroot()
    osm.set('generator', 'retag.py')
    count=0
    countall=0
    tmpl="{a[addr:housenumber]}\t{a[addr:street]}\t{a[addr:city]}\t{a[addr:state]}\t{a[addr:postcode]}\t{a[contact:pobox]}\t{}\t{}\t{}\n"
    dump=open("dump.txt","w")
    cities=set()
    with open("addresses.txt", "w") as log:
        log.write("housenumber\tstreet\tcity\tstate\tpostcode\tpobox\taddress\ttype\tid\n")
        for child in osm:
            countall+=1
            osmid=child.get('id')
            try:
                # check for existing height
                t=child.findall("./tag[@k='address']")
                if len(t) > 1:
                    print("Oh no!")
                elif len(t):
                    address=t[0].get("v")
                    dump.write(address+"\n")
                    items=parse_ma(address)
                    log.write(tmpl.format(tsvquote(address),child.tag,osmid,a={k:tsvquote(v) for k,v in items.items()}))
                    for k,v in items.items():
                        collided=False
                        if v is not None:
                            if k=="addr:city":
                                cities.add(v)
                            exists=child.findall("./tag[@k='{}']".format(k))
                            if len(exists) > 0:
                                oldv=exists[0].get("v")
                                if v==oldv:
                                    continue
                                else:
                                    print("COLLISION",v,exists[0].get("v"),child.tag,osmid)
                                    collided=True
                                    
                            e=ElementTree.Element("tag",attrib={"k":k,"v":v})
                            child.append(e)
                    child.set('action', 'modify')
                    if not collided:
                        child.remove(t[0])
                    count+=1
            except: # addresses not correctly parsed
                #~ print(count)
                log.write("ERROR\t\t\t\t\t\t"+address+"\t"+child.tag+"\t"+osmid+"\n")
                print(child.tag,osmid, address)
                raise
        tree.write(outfile)
        print(count,"items parsed out of",countall)
        #~ print(sorted(cities))

def make_parser():
    parser = argparse.ArgumentParser(description='Split full address data stored in `address` tag into fields.')
    parser.add_argument('osmxml', type=str,
                        help='OSM XML input file')
    parser.add_argument('outfile', type=str,
                        help='Name for modified OSM XML file')
    return parser

if __name__=="__main__":
    ap=make_parser()
    args=ap.parse_args()

    alter_osm(args.osmxml, args.outfile)