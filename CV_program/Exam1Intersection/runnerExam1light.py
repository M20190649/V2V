"""
Program used in the article "Queue length estimation through a simple V2V communication protocol"
"""
from __future__ import absolute_import
from __future__ import print_function

import os
import sys
import optparse
import subprocess
import random
import csv


# the directory where this script resides
THISDIR = os.path.dirname(__file__)


# we need to import python modules from the $SUMO_HOME/tools directory
# If the the environment variable SUMO_HOME is not set, try to locate the python
# modules relative to this script
try:
    # tutorial in tests
    sys.path.append(os.path.join(THISDIR, '..', '..', '..', '..', "tools"))
    sys.path.append(os.path.join(os.environ.get("SUMO_HOME", os.path.join(
        THISDIR, "..", "..", "..")), "tools"))  # tutorial in docs

    import traci
    from sumolib import checkBinary  # noqa
    import randomTrips
except ImportError:
    sys.exit(
        "please declare environment variable 'SUMO_HOME' as the root directory of your sumo installation (it should contain folders 'bin', 'tools' and 'docs')")

class Car_Info:
    def __init__(self,id):
        self.id = id
        self.lasttime = 0
        self.n = {}
        self.St = {}
        self.Ut = {}

class Link_Info:
    def __init__(self,id):
        self.id = id
        self.lasttime = 0
        self.outnum = []
        self.outcount = -1
        self.outflow = 0
        self.inflow = GetEdgeCapacity(id)
        self.outflowhead = 0
        self.innum = []
        self.incount = 0
        self.lastvehs = [0]
        self.queue = 0
    def GetLinkcapacity(self):
        return self.inflow

class Eta:
    def __init__(self):
        self.value = 1.0
        self.hist = [(0,1.0)]
        self.dic = {0:1.0}
    def GetEta(self):
        return self.value
    def CountInconsis(self, carids, carlist, QueueLinkIDs,time):
        num_con = 0
        num_incon = 0
        for linkid in QueueLinkIDs:
            InconPattern = []
            for j in carids:
                car = carlist[j]
                St = 0.0
                Ut = 100000
                CarDic ={}
                if (linkid in car.n.keys()):
                    for n in car.n[linkid]:
                        Car_n_Time = n[0]
                        Car_n_Value = n[1]
                        CarDic[Car_n_Time] = Car_n_Value
                    for st in car.St[linkid]:
                        Car_st_Time = st[0]
                        Car_st_Value = st[1]
                        sum_st_slope = 0
                        for tichan in range(Car_st_Time,time,1):
                            sum_st_slope += self.dic[tichan]*Car_st_Value*1.0
                        newst = CarDic[Car_st_Time] + sum_st_slope
                        if (newst > St):
                            St = CarDic[Car_st_Time] + sum_st_slope
                    for ut in car.Ut[linkid]:
                        Car_ut_Time = ut[0]
                        Car_ut_Value = ut[1]
                        sum_ut_slope = 0
                        for tichan in range(Car_ut_Time,time,1):
                            sum_ut_slope += self.dic[tichan]*Car_ut_Value*1.0
                        newut = CarDic[Car_ut_Time] + sum_ut_slope
                        if (newut < Ut):
                            Ut = CarDic[Car_ut_Time] + sum_ut_slope
                    if (St > Ut):
                        Stpattern = (Car_st_Time, Car_st_Value)
                        Utpattern = (Car_ut_Time, Car_ut_Value)
                        if ((Stpattern not in InconPattern) and (Utpattern not in InconPattern)):
                            num_incon += 1
                            InconPattern.append(Stpattern)
                            InconPattern.append(Utpattern)
                    else:
                        num_con += 1
        return num_incon
    def FixedUpdate(self, carids, carlist, QueueLinkIDs, time, time_interval):
        num_incon = self.CountInconsis(carids, carlist, QueueLinkIDs,time)
        current_eta = self.GetEta()
        if (num_incon == 0):
            next_eta = current_eta * 0.95 #5% down
        else:
            next_eta = current_eta * pow(1.2, num_incon) #20% up
        self.value = next_eta
        self.hist.append((time, next_eta))
        self.dic[time] = next_eta
        return 0
    def Lossfunction(self, carids, carlist, QueueLinkIDs,time):
        U = (ut - st)*(ut - st)
        E = ()
        for linkid in QueueLinkIDs:
            InconPattern = []
            for j in carids:
                car = carlist[j]
                St = 0.0
                Ut = 100000
                CarDic ={}
                if (linkid in car.n.keys()):
                    for n in car.n[linkid]:
                        Car_n_Time = n[0]
                        Car_n_Value = n[1]
                        CarDic[Car_n_Time] = Car_n_Value
                    for st in car.St[linkid]:
                        Car_st_Time = st[0]
                        Car_st_Value = st[1]
                        sum_st_slope = 0
                        for tichan in range(Car_st_Time,time,1):
                            sum_st_slope += self.dic[tichan]*Car_st_Value*1.0
                        newst = CarDic[Car_st_Time] + sum_st_slope
                        if (newst > St):
                            St = CarDic[Car_st_Time] + sum_st_slope
                    for ut in car.Ut[linkid]:
                        Car_ut_Time = ut[0]
                        Car_ut_Value = ut[1]
                        sum_ut_slope = 0
                        for tichan in range(Car_ut_Time,time,1):
                            sum_ut_slope += self.dic[tichan]*Car_ut_Value*1.0
                        newut = CarDic[Car_ut_Time] + sum_ut_slope
                        if (newut < Ut):
                            Ut = CarDic[Car_ut_Time] + sum_ut_slope
                    U = (Ut-St)*(Ut-St)
                    E = ()
        return 0
    def Numericalgradient(self):
        return 0
    def LossUpdate(self):
        return 0
    def csvoutput(self, writer):
        list = self.hist
        header = ["time", "etavalue"]
        writer.writerow(header)
        for i in list:
            time = i[0]
            value = i[1]
            temp = [time, value]
            writer.writerow(temp)




"""V2V update: V2V communication among drivers in the same link."""
# getDistance2D(self, x1, y1, x2, y2, isGeo=False, isDriving=False)
def V2Vupdate(carid, comrange, car_list, netcars, linklist, linkidlist,time, eta):
    tempcar = car_list[carid]
    tempcarPos = traci.vehicle.getPosition(carid)
    temp_group = []
    temp_group.append(tempcar)
    for i in netcars:
        ipos = traci.vehicle.getPosition(i)
        Distance = traci.simulation.getDistance2D(tempcarPos[0], tempcarPos[1], ipos[0], ipos[1], 0, 0)
        if ((Distance > 0) and (Distance <= comrange)):
            temp_group.append(car_list[i])
    if (len(temp_group) >= 2):
        for j in linkidlist:
            n = []
            st = []
            ut = []
            link_vehs = traci.edge.getLastStepVehicleIDs(j)
            for k in temp_group:
                if j in k.n.keys():
                    if (link_vehs != []):
                        if ( k.id == link_vehs[-1] and traci.vehicle.getSpeed(k.id) <= 1.0 and time >= 500):
                            n.append((time, GetQueueLength(k.id, car_list, j, comrange)))
                            st.append((time, -eta.GetEta()*(linklist[j].outflow)))
                            ut.append((time, eta.GetEta()*(linklist[j].inflow - linklist[j].outflow)))
                    n = n + k.n[j]
                    st = st + k.St[j]
                    ut = ut + k.Ut[j]
            nset = set(n)
            stset = set(st)
            utset = set(ut)
            nlist = list(nset)
            stlist = list(stset)
            utlist = list(utset)
            for h in temp_group:
                h.n[j] = nlist
                h.St[j] = stlist
                h.Ut[j] = utlist


"""Information update when CVs exit the link"""
# edgeID:
# edge position: traci.vehicle.getLanePosition(leadvehid)
# h(t) = h(s) / vehicle speed. (timeheadway =spaceheadway/speed)
# flow = 1/timeheadway
# qin = maximam incoming flow = minimum gap it is fixed value
# 1.5m/s
def ExitUpdate(linklist, car_list, linkid, time, outputcarid, comrange, eta):
    if ((outputcarid != 0) and (traci.edge.getLastStepVehicleNumber(linkid) > 3) and outputcarid in traci.vehicle.getIDList()):
        n = GetQueueLength(outputcarid, car_list, linkid, comrange)
        if (n > 0):
            # leadvehid = vehIDs[-1]
            # lastvehid = vehIDs[0]
            # lastvehspeed =  traci.vehicle.getSpeed(lastvehid) #[m/s]
            # lead2Vehspeed = traci.vehicle.getSpeed(lead2Vehid)
            # InDistanceheadwayMin = traci.vehicle.getMinGap(lastvehid) #[m]
            # OutDistanceheadway = traci.vehicle.getDrivingDistance(lead2Vehid, linkid, traci.vehicle.getLanePosition(leadvehid), laneIndex=0) #[m]
            # OutTimeheadway = traci.vehicle.getTau(lastvehid) #OutDistanceheadway / lead2Vehspeed #[s]
            Outflow = linklist[linkid].outflow #veh/s
            Inflowmax = 0.55 #veh/s here, GetlinkCapacity
            tempCar = car_list[outputcarid]
            if (linkid not in tempCar.n.keys() ):
                tempCar.n[linkid]= []
                tempCar.St[linkid] = []
                tempCar.Ut[linkid] = []
            tempCar.n[linkid].append((time, n))
            tempCar.St[linkid].append((time, -eta.GetEta()*Outflow))
            print(Outflow)
            tempCar.Ut[linkid].append((time,eta.GetEta()*(Inflowmax - Outflow)))
            tempCar.lasttime = time
    else:
        print("No car")
    return 0


def GetQueueLength(carid, car_list, linkid, comrange):
    car = car_list[carid]
    carPos = traci.vehicle.getPosition(carid)
    vehIDs = traci.edge.getLastStepVehicleIDs(linkid)
    vehIDs_reverse = traci.edge.getLastStepVehicleIDs(linkid)
    vehIDs_reverse.reverse()
    queue = 0
    platoon = []
    for i in range(len(vehIDs)):
        mae = vehIDs_reverse[i]
        mae_posi = traci.vehicle.getPosition(mae)
        if (traci.simulation.getDistance2D(carPos[0], carPos[1], mae_posi[0], mae_posi[1], 0, 0) > comrange or mae == vehIDs_reverse[-1]):
            break
        ushiro = vehIDs_reverse[i+1]
        ushiro_posi = traci.vehicle.getPosition(ushiro)
        if (i == 0 and traci.simulation.getDistance2D(carPos[0], carPos[1], ushiro_posi[0], ushiro_posi[1], 0, 0) > comrange):
            if (traci.vehicle.getSpeed(mae) <= 5.0):
                queue = 1
                break
            else:
                break
        two_veh_dis = traci.simulation.getDistance2D(mae_posi[0], mae_posi[1], ushiro_posi[0], ushiro_posi[1], 0, 0)
        if (two_veh_dis <= 15):
            if (mae not in platoon):
                platoon.append(mae)
            if (ushiro not in platoon):
                platoon.append(ushiro)
    if (platoon != []):
        for j in platoon:
            if (traci.vehicle.getSpeed(j) <= 5.0):
                queue += 1
    return queue


def GetEdgeCapacity(linkid):
    inflowmaxcurrent = 0.55
    try:
        lanenum = traci.edge.getLaneNumber(linkid)
    except AttributeError:
        lanenum = 1
    capacity = inflowmaxcurrent*lanenum
    return capacity

# ooutput of vehicle information for debugging.
def CsvVehicleOutput():
    return 0

# Time n outflow inflow ,edgeforwardcarst edgeforwardcarut edgebackwardcarst edgebackwardcarut edgeTraveltime edgeaverageflow,
def Csvoutput(writer,time, linklist, car_list,comrange):
    onlyidlist = ["AtoB","BtoA","AtoC","BtoC","CtoCright"]
    if (time == 1):
        name = ["time","queue length n","outflow","inflow","AtoB Lead st","AtoB Lead ut","AtoB last st","AtoB last ut","AtoBTT","AtoBEF","AtoBSpeed","BtoA Lead st","BtoA Lead ut","BtoA last st","BtoA last ut","BtoATT","BtoAEF","BtoASpeed","AtoC Lead st","AtoC Lead ut","AtoC last st","AtoC last ut","AtoCTT","AtoCEF","AtoCSpeed","BtoC Lead st","BtoC Lead ut","BtoC last st","BtoC last ut","BtoCTT","BtoCEF","BtoCSpeed","CtoCright Lead st","CtoCright Lead ut","CtoCright last st","CtoCright last ut","CtoCrightTT","CtoCrightEF","CtoCrightSpeed"]
        writer.writerow(name)
    else:
        val = []
        val.append(time)
        vehicles = traci.edge.getLastStepVehicleIDs("BtoA")
        n = 0
        if (vehicles != []):
            n = GetQueueLength(vehicles[-1], car_list, "BtoA", comrange)
        # n = linklist["BtoA"].queue
        # if (traci.edge.getLastStepHaltingNumber("BtoA") >= 0):
        #     for i in vehicles:
        #         if (traci.vehicle.getSpeed(i) < 5.0):
        #             n += 1
        #             # n = len(vehicles) - vehicles.index(i)
        #             # break
        val.append(n)
        outflowcal = 1.0*1000 * linklist["BtoA"].outcount / traci.simulation.getCurrentTime()
        val.append(outflowcal)
        val.append(0.55)
        for i in onlyidlist:
            if (traci.edge.getLastStepVehicleNumber(i) == 0):
                val.append(0)
                val.append(0)
                val.append(0)
                val.append(0)
                val.append(0)
                val.append(0)
                val.append(0)
            else:
                vehIDs = traci.edge.getLastStepVehicleIDs(i)
                leadvehid = vehIDs[-1]
                leadveh = car_list[leadvehid]
                LeadNdic = {}
                laneid = i + "_0"
                lestvalue = 0
                leutvalue = 100000
                if ("BtoA" in leadveh.n.keys()):
                    for j in leadveh.n["BtoA"]:
                        leadnT = j[0]
                        leadnvalue = j[1]
                        LeadNdic[leadnT] = leadnvalue
                    for lest in leadveh.St["BtoA"]:
                        lestt = lest[0]
                        lestslope = lest[1]
                        newst = LeadNdic[lestt] + lestslope*(time - lestt)
                        if (newst > lestvalue):
                            lestvalue = LeadNdic[lestt] + lestslope*(time - lestt)
                    for leut in leadveh.Ut["BtoA"]:
                        leutt = leut[0]
                        leutslope = leut[1]
                        newut = LeadNdic[leutt] + leutslope*(time - leutt)
                        if (newut < leutvalue):
                            leutvalue = LeadNdic[leutt] + leutslope*(time - leutt)
                    val.append(lestvalue)
                    val.append(leutvalue)
                else:
                    val.append(0)
                    val.append(0)
                lastvehid = vehIDs[0]
                lastveh = car_list[lastvehid]
                LastNdic = {}
                lastvalue = 0
                lautvalue = 100000
                if ("BtoA" in lastveh.n.keys()):
                    for j in lastveh.n["BtoA"]:
                        lastdnT = j[0]
                        lastnvalue = j[1]
                        LastNdic[lastdnT] = lastnvalue
                    for last in lastveh.St["BtoA"]:
                        lastt = last[0]
                        lastslope = last[1]
                        newlast = LastNdic[lastt] + lastslope*(time - lastt)
                        if (newlast > lastvalue):
                            lastvalue = LastNdic[lastt] + lastslope*(time - lastt)
                    for laut in lastveh.Ut["BtoA"]:
                        lautt = laut[0]
                        lautslope = laut[1]
                        newlaut = LastNdic[lautt] + lautslope*(time - lautt)
                        if (newlaut < lautvalue):
                            lautvalue = LastNdic[lautt] + lautslope*(time - lautt)
                    val.append(lastvalue)
                    val.append(lautvalue)
                else:
                    val.append(0)
                    val.append(0)
                val.append(traci.edge.getTraveltime(i))
                flow = traci.edge.getLastStepVehicleNumber(i) / traci.lane.getLength(laneid) * traci.edge.getLastStepMeanSpeed(i)
                val.append(linklist[i].outflow)
                val.append(traci.edge.getLastStepMeanSpeed(i))
        writer.writerow(val)
    return 0



def run():
    """execute the TraCI control loop"""
    # Link list
    Link_id_list = traci.edge.getIDList()
    Link_list = {}
    QueueLinkIDs = []
    for i in Link_id_list:
        Link_list[i] = Link_Info(i)
    # Car_list
    print(Link_list)
    Car_list = {}
    # eta
    eta = Eta()
    # main loop. do something every simulation step until no more vehicles are
    # loaded or running
    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()
        time = traci.simulation.getCurrentTime()/1000
        for carid in traci.vehicle.getIDList():
            if carid not in Car_list.keys():
                Car_list[carid] = Car_Info(carid)
        # link inflow and outflow Update
        for j in traci.edge.getIDList():
            CurrentVehs = traci.edge.getLastStepVehicleIDs(j)
            temp_link = Link_list[j]
            if (CurrentVehs != []):
                temp_link.queue = GetQueueLength(CurrentVehs[-1], Car_list, "BtoA", communication_range)
                if (CurrentVehs[-1] != temp_link.lastvehs[-1]):
                    temp_link.outcount += 1
                    temp_out = (traci.simulation.getCurrentTime()/1000,temp_link.outcount)
                    headway = traci.simulation.getCurrentTime()/1000 - temp_link.lasttime
                    temp_link.outflow = 1.0*1000 * temp_link.outcount / traci.simulation.getCurrentTime()
                    # temp_link.outflowhead = 1.0 / headway
                    temp_link.outnum.append(temp_out)
                    outputCar = temp_link.lastvehs[-1]
                    temp_link.lasttime = traci.simulation.getCurrentTime()/1000
                    ExitUpdate(Link_list, Car_list,j,time,outputCar,communication_range,eta)
                    temp_link.lastvehs = CurrentVehs
        for h in traci.vehicle.getIDList():
            V2Vupdate(h, communication_range, Car_list, traci.vehicle.getIDList(), Link_list, Link_id_list,time,eta)
        eta.FixedUpdate(traci.vehicle.getIDList(), Car_list, ["BtoA"], time, 1)
        Csvoutput(csvWriter,time, Link_list, Car_list, communication_range)
        if (time == 1200):
            eta.csvoutput(etawriter)
    sys.stdout.flush()
    traci.close()

def get_options():
    """define options for this script and interpret the command line"""
    optParser = optparse.OptionParser()
    optParser.add_option("--nogui", action="store_true",
                         default=False, help="run the commandline version of sumo")
    options, args = optParser.parse_args()
    return options


# this is the main entry point of this script
if __name__ == "__main__":
    # load whether to run with or without GUI
    options = get_options()

    # this script has been called from the command line. It will start sumo as a
    # server, then connect and run
    if options.nogui:
        sumoBinary = checkBinary('sumo')
    else:
        sumoBinary = checkBinary('sumo-gui')

    net = 'exam1light.net.xml'
    communication_range = 50
    f = open('Infolight20190624_range50_etatest.csv',"w")
    csvWriter = csv.writer(f)
    ff = open('etaInfolight20190624_range50_etatest.csv',"w")
    etawriter = csv.writer(ff)
    # this is the normal way of using traci. sumo is started as a
    # subprocess and then the python script connects and runs
    traci.start([sumoBinary, '-c', 'exam1light.sumocfg', '--queue-output', 'queue.xml'])
    run()
    f.close()
