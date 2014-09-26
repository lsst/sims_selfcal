"""
modtranCards

Based on Michel's Makecard2A.py, modified to class structure & deal with single run at a time,
while removing hard-coded paths.

This class provides methods to translate atmospheric parameter inputs (generated by modtranSequences)
into the MODTRAN input .tp5 files, including the optional Card 2A (for cirrus clouds) and the
(required for us) card 2B to specify aerosol features.  The methods for writing these cards are
based on code written by Michel Creze. In MODTRAN speak, a 'card' is the information related to a single
entry for MODTRAN (and is usually a 'line'). What Michel called a 'rank' can be translated to which 'line'
this card is on in the .tp5 file.  The entire tp5 (tape5) file is a series of 'cards'.

The class also provides a method to spawn a shell process to run MODTRAN (assuming you have the external
MODTRAN program and license).

The file Cardtemplate.dat provides the base template for the MODTRAN .tp5 file, and is kept in
${ATMOSPHERES_TRANSMISSION_DIR}/data. The file ParameterFormats.dat specifies information on the
parameters which can be changed in the .tp5 file (at least, what can be changed using the parameters
expected to be generated by modtranSequences.py).


ljones@astro.washington.edu


"""

import os
import warnings
import subprocess
import shlex
from copy import deepcopy
import numpy

class ModtranCards:
    """A class to set up the MODTRAN4 or 5 .tp5 input files, and run MODTRAN. """
    def __init__(self):
        """Instantiate the modtranCard object."""
        self._cardTemplate = None
        self._paramFormats = None
        self.paramValues = None
        return

    def setDefaults(self):
        self.readCardTemplate()
        self.readParameterFormats()

    def readCardTemplate(self, templatefile=None):
        """Read the default .tp5 template file for a run.
        This has the benefit that parameters which are not changed by our setup are left in the default state."""
        # (although, the string-slicing that results may not be the easiest thing to read)
        # Set up the default file location.
        if templatefile == None:
            dataDir = os.getenv('ATMOSPHERE_TRANSMISSION_DIR')
            if dataDir == None:
                raise Exception('If ATMOSPHERE_TRANSMISSION_DIR env not set, must specify template filename.')
            templatefile = os.path.join(dataDir, 'data/Cardtemplate.dat')
        # Read the file, store the info.
        file = open(templatefile, 'r')
        self._cardTemplate = []
        for line in file:
            self._cardTemplate.append(line)
        file.close()
        # _cardTemplate is a list, with each line from the template file as a string element of that list.
        return

    def readParameterFormats(self, formatfile=None):
        """Read the format file for the parameters we can change in each run.
        This provides the names of changeable parameters, their location in the run .tp5 file and data format."""
        # Using the same format established by Michel.
        # Set up the default file location.
        if formatfile == None:
            dataDir = os.getenv('ATMOSPHERE_TRANSMISSION_DIR')
            if dataDir == None:
                raise Exception('If ATMOSPHERE_TRANSMISSION_DIR env not set, must specify format filename.')
            formatfile = os.path.join(dataDir, 'data/FormatParameters.dat')
        # Read the file, store the info.
        file = open(formatfile, 'r')
        self._paramFormats = {}
        for line in file:
            values = line.split()
            paramName = values[0]
            self._paramFormats[paramName] = {}
            self._paramFormats[paramName]['outputLine'] = int(values[1])
            self._paramFormats[paramName]['format'] = values[2]
            if self._paramFormats[paramName]['format'].endswith('d'):
                self._paramFormats[paramName]['type'] = int
            elif self._paramFormats[paramName]['format'].endswith('f'):
                self._paramFormats[paramName]['type'] = float
            else:
                self._paramFormats[paramName]['type'] = str
            self._paramFormats[paramName]['startChar'] = int(values[3])
            self._paramFormats[paramName]['endChar'] = int(values[4])
        file.close()
        # _paramFormats is a dictionary, where each entry is keyed to a parameter that can be changed in the
        # .tp5 file. Each dictionary entry is itself a dictionary, storing the line ('outputLine') in the MODTRAN
        #  .tp5 file where the data will be changed, along with the starting and ending character values ('startChar',
        #  'endChar') and the data format ('format', although we only use the data type currently).
        return

    def readParamValues_M(self, parameterfile):
        """Read the parameters from a file (with Michel's input format, 'id $ key = value $ ... ').
        Provided for backward compatibility & testing purposes mainly. """
        file = open(parameterfile, 'r')
        # Save the parameter values to a list of dictionaries, because there will likely be more than one MODTRAN 'run'
        #  to be generated if running in this manner.
        paramValuesList = []
        for line in file:
            paramValuesDict = {}
            # The current format version of Michel's parameter file is values separated by $, with additional spaces
            #  on either side of entries like 'ID85144469 $ expMJD = 49353.165757 $ fieldRA = 0.793502 $ fi ..'
            tmpvalues = line.split('$')
            # The first item is the observation ID name
            paramValuesDict['id'] = tmpvalues[0].strip()
            # The other values are keyword-value pairs.
            for i in range(1, len(tmpvalues)):
                # Avoid entries which aren't actually key-value pairs (like the newline at the end of the line)
                if (len(tmpvalues[i]) < 3):
                    continue
                values = tmpvalues[i].split('=')
                parname = values[0].strip()  #strip off spaces
                parvalue = values[1].strip()
                paramValuesDict[parname] = parvalue
            # Then add this dictionary to the list.
            paramValuesList.append(paramValuesDict)
        file.close()
        return paramValuesList

    def readParamValues_F(self, parameterfile):
        """Read the parameters from a flat file format (file headers, then values in each column).
        Provided for backward compatibility & testing purposes mainly.  """
        file = open(parameterfile, 'r')
        # Save the parameter values to a list of dictionaries.
        paramValuesList = []
        keys = None
        for line in file:
            if line.startswith('#'):
                # This is the header line, so get the dictionary key names.
                line = line.lstrip('#')
                keys = line.split()
                continue
            if keys == None:
                raise Exception('Could not get dictionary keys from file header line (%s)' %(line))
            paramValuesDict = {}
            values = line.split()
            for k, i in zip(keys, len(keys)):
                paramValuesDict[k] = values[i]
            paramValuesList.append(paramValuesDict)
        file.close()
        return paramValuesList

    def _validateParamValues(self, paramValuesDict):
        """Given a dictionary of parameters which will be changed for the modtran card,
        validate against format file and store in class."""
        keys_used = []
        # Check what keys are in dictionary that we should use.
        for parname in paramValuesDict.keys():
            if parname in self._paramFormats.keys():
                # Add to list of parameters to put into input card.
                keys_used.append(parname)
                # And convert to appropriate type.
                paramValuesDict[parname] = self._paramFormats[parname]['type'](paramValuesDict[parname])
        return keys_used

    def _printCards(self, runCards):
        "Pretty print the cards to the screen for debugging."""
        for run in runCards:
            for card in run:
                print card.rstrip()
        return

    def writeModtranCards(self, paramValues, outfileRoot='tmp'):
        """Write the modtran run card to disk.
        Parameter values can be provided in a single dictionary, or as a list of dictionaries (for multiple runs)."""
        # If paramValues was a single dictionary, let's just turn it into a list so we can iterate
        #  over as if it was given as a list. Cheap, but easy.
        if isinstance(paramValues, dict):
            paramValues = [paramValues,]
        # Add some more modtran values to be written into cards.
        # Define optional card2A and/or Card2B to be inserted after card2
        #   In case clouds are expected: Default values for Cirrus 18 or 19
        card2A =  ['   0.000   0.000   0.000      ' + '                              ' + '                    \n']
        #   In case aerosols are non standard: aerosol fog near surface, decreasing with height
        card2B = ['    -1.000     2.000     1.000 ' + '                              ' + '                   \n']
        # Modtran has a 'continuation' card that indicates if there are more atmospheres remaining to be
        # run in the input file, so let's set those values.
        continuation_cardvalue = numpy.ones(len(paramValues), 'int')
        continuation_cardvalue[len(continuation_cardvalue)-1] = 0
        continuation_cardline = len(self._cardTemplate) - 1
        # We want to write the location of the MODTRAN DATA files into the input file, so let's figure that out.
        modtranDataDir = os.getenv('MODTRAN_DATADIR')
        # Go through each 'run', combining the input cards into one big file.
        irun = 0
        allcards = []
        for paramValuesDict in paramValues:
            # Validate the dictionary contains only parameters we can understand.
            paramkeys = self._validateParamValues(paramValuesDict)
            # Set up the base modtran run input values.
            card = deepcopy(self._cardTemplate)
            # Go through parameter key/values that we know how to use in modtran file, add to input file.
            for k in paramkeys:
                line = self._paramFormats[k]['outputLine']
                # Insert into appropriate card.
                card[line] = card[line][0:(self._paramFormats[k]['startChar']-1)] + \
                    self._paramFormats[k]['format'] %(paramValuesDict[k]) + \
                    card[line][(self._paramFormats[k]['endChar']):]
            # Change modtran Data Dir
            #   this line should be 2 if the band model is not being specified; 3 if it is.
            card[3] = modtranDataDir + '\n'
            # Add continuation card value.
            card[continuation_cardline] = card[continuation_cardline][:4] + '%d' %(continuation_cardvalue[irun]) + \
                card[continuation_cardline][5:]
            # Add Card2A and/or Card 2B if needed, inserting into the input file at line ('rank') 6
            # And add these lines into the modtran input file at line ('rank') 6
            line_add = 6
            if paramValuesDict['IHAZE'] > 0 :
                if paramValuesDict['ICLD'] > 0 :
                    # Insert card 2A
                    card = card[:line_add] + card2A + card[line_add:]
                    line_add += 1
                if paramValuesDict['IVSA'] > 0:
                    card = card[:line_add] + card2B + card[line_add:]
            # Add new card into entire list.
            irun += 1
            allcards.append(card)
            #self._printCards(allcards)
        # Write data to output.
        file = open(outfileRoot+'.tp5', 'w')
        for run in allcards:
            for card in run:
                file.write(card)
        file.close()
        return

    def runModtran(self, outfileRoot='tmp'):
        """Spawn a shell process to run MODTRAN on the input file in outfileRoot. """
        # Get name of command.
        modtranExecutable = os.getenv('MODTRAN_EXECUTABLE')
        args = shlex.split(modtranExecutable)
        # Write name of modtran .tp5 file to run, and put into mod5root.in input file.
        file = open('mod5root.in', 'w')
        print >>file, outfileRoot
        file.close()
        # Run modtran.
        errcode = subprocess.check_call(args)
        if errcode != 0:
            raise Exception('Modtran run on %s did not complete properly.' %(outfileRoot))
        return

    def cleanModtran(self, outfileRoot='tmp'):
        """Spawn a shell process to clean up all modtran files starting with outfileRoot."""
        # MODTRAN suffixes:
        suffixes = ['.tp5', '.tp7', '.7sc', '.psc', '.plt']
        deleteFiles = []
        for s in suffixes:
            deleteFiles.append(outfileRoot + s)
        deleteFiles.append('mod5root.in')
        command = '/bin/rm '
        for d in deleteFiles:
            command = command + d + ' '
        args = shlex.split(command)
        subprocess.check_call(args)
        return

