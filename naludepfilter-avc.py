#!/usr/bin/env python

#
#  Copyright 2009 Claudio Pisa (claudio dot pisa at uniroma2 dot it)
#
#  This file is part of SVEF (SVC Streaming Evaluation Framework).
#
#  SVEF is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  SVEF is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with SVEF.  If not, see <http://www.gnu.org/licenses/>.
#

# This script takes in input the original trace file and the received trace file (i.e. with
# some lines missing) and attempts to delete the lines from the received trace file that
# depend on lines that have been lost during the transmission.

import sys
from nalulib import *

if(len(sys.argv) < 3):
		print """
		Filter the NAL units that have unsatisfied dependencies. AVC version.

		Usage: %s <sent stream trace file> <received trace file>   >   <filtered trace file>

		Where:

		<sent stream trace file>: the trace file obtained from the "-pt" option
		of the JSVM BitstreamExtractor tool using the sent H.264 as the
		argument, or from the purgeLastGOP.py script. For example:
		$ BitstreamExtractorStatic -pt originaltrace.txt foreman.264
		$ purgeLastGOP.py originaldecoderoutput.txt originaltrace.txt > originaltrace-nolastgop.txt

		<received trace file>: the trace file obtained from the /receiver/
		module. For example:
		$ ./receiver 4455 out.264 20000 > receivedtrace.txt

		Example:
		%s originaltrace-nolastgop.txt receivedtrace.txt > filteredtrace.txt

		""" % (sys.argv[0], sys.argv[0])
		sys.exit(1)

originaltracefilename = sys.argv[1] 
receivedtracefilename = sys.argv[2]


# load lines from the original trace file
originaltracefile = open(originaltracefilename)
originalnalulist = [] 
originalnaluheader = []
originalnaludict = {}
for line in originaltracefile:
		nalu = NALU(line)
		if nalu.packettype == "SliceData":
				originalnalulist.append(nalu)
				originalnaludict.update({nalu.id: nalu})
		else:
				originalnaluheader.append(nalu)

originaltracefile.close()

# load lines from the received trace file
receivedtracefile = open(receivedtracefilename)
receivednalulist = [] 
receivednaluidset = set()
for line in receivedtracefile:
		nalu = NALU(line)
		nalu.ok = True # to mark lines as deleted or not
		if nalu.packettype == "SliceData":
				receivednalulist.append(nalu)
				assert not nalu.id in receivednaluidset
				receivednaluidset.add(nalu.id)

receivedtracefile.close()


#              
#   |   +----+ 
#   |   |  + | 
#   |   +--|-+ 
# T |      |
# i |   +--|-+ 
# d |   |  + | 
#   |   +--|-+ 
#   |      |
#   |   +--|-+ 
#   |   |  V | 
#   |   +----+ 
#   V

# create NALU dependency trees, one per GOP
# filter out control NALUs
filterednalus = [nalu for nalu in originalnalulist if not nalu.isControlNALU()]

# first pass to find slice-paired NALUs
j = 0
while j < len(filterednalus):
		nalu1 = filterednalus[j]
		nalu2 = filterednalus[j+1]
		assert nalu1.tid == nalu2.tid
		nalu1.parents.append(nalu2.id)
		nalu2.parents.append(nalu1.id)
		j+=2

j = 0
while j < len(filterednalus):
		gophead = j
		j+=1
		while j < len(filterednalus) and not filterednalus[j].isGOPHead():
				j += 1
		currentgop = filterednalus[gophead: j]
		assert len(currentgop) == 0 or currentgop[0].isGOPHead()
		
		# scan departing from the end
		currentgop.reverse()
		i = 0
		while i < len(currentgop):
				nalu = currentgop[i]
				assert len(nalu.parents) == 1
				for parentavcid in nalu.getAVCParentsIds():
						found = False
						k = i 
						while not found and k < len(currentgop):
								if currentgop[k].getAVCId() == parentavcid and not currentgop[k].id in nalu.parents and currentgop[k].id != nalu.id:
										nalu.parents.append(currentgop[k].id)
										found = True
								k += 1
				i += 1 

# now scan the received NALUs until the end of the GOP
for recnalu in receivednalulist:
		if not recnalu.isControlNALU():
				corrnalu = originalnaludict[recnalu.id]
				for parentid in corrnalu.parents:
						if not parentid in receivednaluidset:
								try:
										receivednaluidset.remove(recnalu.id) #delete from receivednaluidset
								except KeyError:
										assert recnalu.ok == False
								recnalu.ok = False	#mark for deletion


#second pass to delete duplicate control NALUs
updatedreceivednalulist = [nalu for nalu in receivednalulist if nalu.ok]
i = 0
while i < len(updatedreceivednalulist) - 2:
		if updatedreceivednalulist[i].isControlNALU() and updatedreceivednalulist[i+1].isControlNALU():
					updatedreceivednalulist[i].ok = False
		i+=1
						

#third pass to check if control NALUs are followed by the right NALUs
reupdatedreceivednalulist = [nalu for nalu in updatedreceivednalulist if nalu.ok]
i = 0
while i < len(reupdatedreceivednalulist) - 2:
		if reupdatedreceivednalulist[i].isControlNALU():
					if reupdatedreceivednalulist[i+1].lid != reupdatedreceivednalulist[i].lid:
						reupdatedreceivednalulist[i].ok = False
					elif reupdatedreceivednalulist[i+1].tid != reupdatedreceivednalulist[i].tid:
						reupdatedreceivednalulist[i].ok = False
		i+=1

#fourth pass to see if the last nalu is a control nalu
rereupdatedreceivednalulist = [nalu for nalu in reupdatedreceivednalulist if nalu.ok] 
i=-1
nalu = rereupdatedreceivednalulist[i]
while nalu.isControlNALU():
		nalu.ok = False
		i -= 1
		nalu = rereupdatedreceivednalulist[i]


#count and list deleted packets
deletednalulist = [nalu for nalu in receivednalulist if not nalu.ok]
print >> sys.stderr, "Number of packets deleted: %d" % len(deletednalulist)
for nalu in deletednalulist:
		print >> sys.stderr, nalu


#update the received packet list and print it
newupdatedreceivednalulist = [nalu for nalu in receivednalulist if nalu.ok]
print "Start-Pos.  Length  LId  TId  QId   Packet-Type  Discardable  Truncatable"
print "==========  ======  ===  ===  ===  ============  ===========  ==========="
for nalu in [nalu for nalu in originalnaluheader if nalu.id > -1]:
		print nalu
for nalu in newupdatedreceivednalulist:
		print nalu
		

print >> sys.stderr, "Number of packets deleted: %d" % len(deletednalulist)

