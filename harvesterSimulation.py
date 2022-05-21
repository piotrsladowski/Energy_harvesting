import argparse
import logging
import pathlib
import csv
import traceback
from enum import Enum
import time
from datetime import datetime
from collections import OrderedDict
import bisect
import json

class harvester():
    simulationStep = 300 # 5*60
    CSVFileName = None
    batteryLvl = None
    batteryLvlKeys = []
    batteryCapacity = None
    batteryCapacityKeys = []
    socEnergyUsage = None
    socEnergyUsageKeys = []
    isOperational = None
    isOperationalKeys = []
    insolationData = None
    insolationDataKeys = []
    windData = None
    windDataKeys = []
    simulationStart = None
    simulationEnd = None
    skyParameter = None

    solarPaneArea = float(0.5) # m^2
    solarPaneEfficiency = float(0.15)
    capacity = 1 # Wh
    
    def __init__(self) -> None:
        parser = argparse.ArgumentParser(description='TODO')
        parser.add_argument('-i', '--insolation', help='Input CSV file with insolation data.')
        parser.add_argument('-s', '--start', help='Simulation start time (unix timestamp)')
        parser.add_argument('-e', '--end', help='Simulation end time (unix timestamp).')
        args = parser.parse_args()

        self.simulationEnd = int(time.time())
        self.simulationStart = self.simulationEnd - 2628000 * 3
        self.skyParameter = typeOfSkyProblem.TOA

        if args.insolation:
            self.CSVFileName = str(args.insolation)
        
        self.CSVFileName = 'test.csv'
        self.run()


    def initializeDicts(self) -> None:
        self.batteryLvl = OrderedDict()
        self.insolationData = OrderedDict()
        self.windData = OrderedDict()
        self.batteryCapacity = OrderedDict()
        self.isOperational = OrderedDict()
        self.socEnergyUsage = OrderedDict()


        if ((self.simulationEnd - self.simulationStart) % self.simulationStep) != 0:
            self.simulationStart = self.simulationStart - (self.simulationEnd - self.simulationStart) % self.simulationStep
        for i in range(self.simulationStart, self.simulationEnd + self.simulationStep, self.simulationStep):
            self.batteryLvl[i] = 0
            self.insolationData[i] = 0
            self.windData[i] = 0
            self.batteryCapacity[i] = 0
            self.isOperational[i] = 1
            self.socEnergyUsage[i] = 0

        self.batteryLvl[self.simulationStart] = 100
        self.batteryLvlKeys = [*self.batteryLvl]
        self.insolationDataKeys = [*self.insolationData]
        self.windDataKeys = [*self.windData]
        self.batteryCapacityKeys = [*self.batteryCapacity]
        self.isOperationalKeys = [*self.isOperational]
        self.socEnergyUsageKeys = [*self.socEnergyUsage]

        self.batteryCapacity[self.simulationStart] = self.capacity
            


    def run(self) -> None:
        self.initializeDicts()
        self.readInsolationCSV()
        self.calculatePowerUsage()
        self.combineSources()
        self.saveResultsToFile()

    def readInsolationCSV(self) -> None:
        if self.CSVFileName is not None:
            with open(self.CSVFileName, 'r') as r_obj:
                csv_reader = csv.reader(r_obj, delimiter=';')
                for row in csv_reader:
                    if row[0][0] != "#":
                        timeLimits = row[0].split('/')
                        timeLimits[0] = timeLimits[0].split('.')[0] # Remove unnecesary resolution
                        timeLimits[1] = timeLimits[1].split('.')[0]
                        observationPeriodStart = datetime.strptime(timeLimits[0], "%Y-%m-%dT%H:%M:%S").timestamp()
                        observationPeriodEnd = datetime.strptime(timeLimits[1], "%Y-%m-%dT%H:%M:%S").timestamp()
                        timestampBetween = self.between(self.batteryLvlKeys, observationPeriodStart, observationPeriodEnd)
                        for i in timestampBetween:
                            
                            self.insolationData[i] = float(row[self.skyParameter]) * (self.simulationStep / 3600) * self.solarPaneArea * self.solarPaneEfficiency * 20
        else:
            raise NotImplementedError

    def degradateBattery(self, i: int) -> None:
        try:
            currentLvl = self.batteryLvl[i]
            previousLvl = self.batteryLvl[i-self.simulationStep]
            diff = currentLvl - previousLvl
            if diff >= 0:
                self.batteryCapacity[i+self.simulationStep] = self.batteryCapacity[i]
                return
            if diff > -10:
                self.batteryCapacity[i+self.simulationStep] = self.batteryCapacity[i-self.simulationStep] * 0.99999
                return
            if diff > -30:
                self.batteryCapacity[i+self.simulationStep] = self.batteryCapacity[i-self.simulationStep] * 0.99998
                return
            if diff > -50:
                self.batteryCapacity[i+self.simulationStep] = self.batteryCapacity[i-self.simulationStep] * 0.99997
                return
            if diff > -70:
                self.batteryCapacity[i+self.simulationStep] = self.batteryCapacity[i-self.simulationStep] * 0.99996
                return
            if diff > -90:
                self.batteryCapacity[i+self.simulationStep] = self.batteryCapacity[i-self.simulationStep] * 0.99995
                return
        except KeyError:
            self.batteryCapacity[i+self.simulationStep] = self.batteryCapacity[i]

    def calculatePowerUsage(self) -> None:
        socEnergyUsageSleepMode = 2.35 * 3 * 0.000001 * 5 # 2.35uA * 3V * 5 minutes in Wh
        o = 0
        for i in range(self.simulationStart, self.simulationEnd + self.simulationStep, self.simulationStep):
            o = o + 1
            calculatedUsage = None
            if (o % 3) == 0:
                calculatedUsage = socEnergyUsageSleepMode
            else:
                calculatedUsage = socEnergyUsageSleepMode + ((8.3 + 10.8) * 3 * 0.0001) * 5
            self.socEnergyUsage[i] = calculatedUsage

    def combineSources(self) -> None:
        for i in range(self.simulationStart, self.simulationEnd + self.simulationStep, self.simulationStep):
            if (self.batteryLvl[i] < 5):
                self.isOperational[i] = 0
            else:
                relativeBatteryUsage = self.socEnergyUsage[i] / self.batteryCapacity[i]
                if relativeBatteryUsage < self.batteryLvl[i]:
                    self.batteryLvl[i] = self.batteryLvl[i] - relativeBatteryUsage
                else:
                    self.batteryLvl[i] = 0
            self.degradateBattery(i)
            relativeNewEnergy = self.insolationData[i] / self.batteryCapacity[i]
            
            if relativeNewEnergy + self.batteryLvl[i] >= 100:
                self.batteryLvl[i + self.simulationStep] = 100
            else:
                self.batteryLvl[i + self.simulationStep] = self.batteryLvl[i] + relativeNewEnergy

    def between(self, l1, low, high):
        l2 = []
        for i in l1:
            if(i >= low and i < high):
                l2.append(i)
        return l2

    def saveResultsToFile(self) -> None:
        with open('result.json', 'w') as fp:
            json.dump(self.batteryLvl, fp)
        with open('soc.json', 'w') as fp:
            json.dump(self.socEnergyUsage, fp)
        with open('cap.json', 'w') as fp:
            json.dump(self.batteryCapacity, fp)

        with open('batLvl.csv', 'w', newline='') as csvfile:
            csv_columns = ['timestamp','value']
            writer = csv.writer(csvfile)
            writer.writerow(csv_columns)
            for data in self.batteryLvl.items():
                writer.writerow(data)

        with open('soc.csv', 'w', newline='') as csvfile:
            csv_columns = ['timestamp','value']
            writer = csv.writer(csvfile)
            writer.writerow(csv_columns)
            for data in self.socEnergyUsage.items():
                writer.writerow(data)

        with open('cap.csv', 'w', newline='') as csvfile:
            csv_columns = ['timestamp','value']
            writer = csv.writer(csvfile)
            writer.writerow(csv_columns)
            for data in self.batteryCapacity.items():
                writer.writerow(data)

        with open('insolation.csv', 'w', newline='') as csvfile:
            csv_columns = ['timestamp','value']
            writer = csv.writer(csvfile)
            writer.writerow(csv_columns)
            for data in self.insolationData.items():
                writer.writerow(data)

        with open('op.csv', 'w', newline='') as csvfile:
            csv_columns = ['timestamp','value']
            writer = csv.writer(csvfile)
            writer.writerow(csv_columns)
            for data in self.isOperational.items():
                writer.writerow(data)
        """with open('batLvl.csv', 'w') as csvfile:
            csv_columns = ['timestamp','value']
            writer = DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            for k, v in self.batteryLvl.items(): # without items you have only access to keys here
                writer.writerow('keys': k, 'values': v)"""

class typeOfSkyProblem():
    TOA = 1
    ClearSkyGHI = 2
    ClearSkyBHI = 3
    ClearSkyDHI = 4
    ClearSkyBNI = 5
    GHI = 6
    BHI = 7
    DHI = 8
    BNI = 9

if __name__ == "__main__":
    harvester = harvester()