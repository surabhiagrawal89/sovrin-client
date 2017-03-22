import os

from ioflo.base.consoling import Console

from plenum.common.log import Logger, getlogger
from sovrin_client.agent.agent import runBootstrap, WalletedAgent
from sovrin_client.agent.runnable_agent import RunnableAgent

from plenum.common.txn import NAME, VERSION

from anoncreds.protocol.types import ID
from sovrin_client.agent.exception import NonceNotFound
from sovrin_client.client.client import Client
from sovrin_client.client.wallet.wallet import Wallet
from sovrin_client.test.helper import primes
from sovrin_common.config import agentLoggingLevel
from sovrin_common.config_util import getConfig


class BaseAgent(WalletedAgent, RunnableAgent):
    def __init__(self,
                 name: str,
                 basedirpath: str,
                 client: Client = None,
                 wallet: Wallet = None,
                 port: int = None,
                 loop=None):

        if not basedirpath:
            config = getConfig()
            basedirpath = basedirpath or os.path.expanduser(config.baseDir)

        portParam, = self.get_passed_args()

        super().__init__(name, basedirpath, client, wallet,
                         portParam or port, loop=loop)

        self.claimVersionNumber = 0.01

        self.logger = getlogger()

        # available claims to anyone whos connection is accepted by the agent
        self.availableClaimsToAll = []

        # available claims only for certain invitation (by nonce)
        self.availableClaimsByNonce = {}

        # mapping between specific identifier and available claims which would
        # have been available once they have provided requested information
        # like proof etc.

        self.availableClaimsByIdentifier = {}

        self.updateClaimVersionFile(self.getClaimVersionFileName())

    def getClaimVersionFileName(self):
        return self.name.replace(" ","-").lower() + "-schema-version.txt"

    def updateClaimVersionFile(self, fileName,):
        claimVersionFilePath = '{}/{}'.format(self._basedirpath, fileName)
        # get version number from file
        if os.path.isfile(claimVersionFilePath):
            try:
                with open(claimVersionFilePath, mode='r+') as file:
                    claimVersionNumber = float(file.read()) + 0.001
                    file.seek(0)
                    # increment version and update file
                    file.write(str(claimVersionNumber))
                    file.truncate()
            except OSError as e:
                self.logger.warn('Error occurred while reading version file: '
                                 'error:{}'.format(e))
                raise e
            except ValueError as e:
                self.logger.warn('Invalid version number')
                raise e
        else:
            try:
                with open(claimVersionFilePath, mode='w') as file:
                    file.write(str(self.claimVersionNumber))
            except OSError as e:
                self.logger.warn('Error creating version file {}'.format(e))
                raise e

    def setupLogging(self, filePath):
        Logger().setLogLevel(agentLoggingLevel)
        Logger().enableFileLogging(filePath)
        self.setupRaetLogging(Console.Wordage.concise)

    def setupRaetLogging(self, level):
        Logger().setupRaet(raet_log_level=level)

    def getInternalIdByInvitedNonce(self, nonce):
        if nonce in self._invites:
            return self._invites[nonce]
        else:
            raise NonceNotFound

    # def get_available_claim_list(self, link):
    #     assert link
    #     assert link.invitationNonce
    #     assert link.remoteIdentifier
    #     return self.availableClaimsToAll + \
    #            self.availableClaimsByNonce.get(link.invitationNonce, []) + \
    #            self.availableClaimsByIdentifier.get(link.remoteIdentifier, [])
    #
    # def getSchemaKeysToBeGenerated(self):
    #     raise NotImplemented
    #
    # def getSchemaKeysForClaimsAvailableToAll(self):
    #     return self.getSchemaKeysToBeGenerated()
    #
    # def getSchemaKeysForClaimsAvailableToSpecificNonce(self):
    #     return {}

    # def getAttrDefs(self):
    #     raise NotImplemented

    # def getAttrs(self):
    #     raise NotImplemented

    async def postClaimVerif(self, claimName, link, frm):
        pass

    async def initAvailableClaimList(self):
        async def getSchema(schemaKey):
            schema = await self.issuer.wallet.getSchema(ID(schemaKey))
            return {
                NAME: schema.name,
                VERSION: schema.version,
                "schemaSeqNo": schema.seqId
            }

        for schemaKey in self.getSchemaKeysForClaimsAvailableToAll():
            schema = await getSchema(schemaKey)
            self.availableClaimsToAll.append(schema)

        for nonce, schemaNames in self.getSchemaKeysForClaimsAvailableToSpecificNonce().items():
            for schemaName in schemaNames:
                schemaKeys = list(filter(lambda sk: sk.name ==schemaName, self.getSchemaKeysToBeGenerated()))
                assert len(schemaKeys) == 1, \
                    "no such schema name found in generated schema keys"
                schema = await getSchema(schemaKeys[0])
                oldAvailClaims = self.availableClaimsByNonce.get(nonce, [])
                oldAvailClaims.append(schema)
                self.availableClaimsByNonce[nonce] = oldAvailClaims

    # def _addAttribute(self, schemaKey, proverId, link):
    #     attr = self.getAttrs()[self.getInternalIdByInvitedNonce(proverId)]
    #     self.issuer._attrRepo.addAttributes(schemaKey=schemaKey,
    #                                         userId=proverId,
    #                                         attributes=attr)

    async def add_schemas_to_wallet(self):
        for schemaKey in self.getSchemaKeysToBeGenerated():
            schema_id = self.publish_schema('basic',
                                            schemaKey.name,
                                            '1.0')

            _, _ = self.publish_issuer_keys(schema_id,
                                            p_prime=primes["prime1"][0],
                                            q_prime=primes["prime1"][1])
            self.publish_revocation_registry(schema_id=schema_id)

        # for schemaKey in self.getSchemaKeysToBeGenerated():
        #     matchedAttrDefs = list(filter(lambda ad: ad.name == schemaKey.name,
        #                      self.getAttrDefs()))
        #     assert len(matchedAttrDefs) == 1, \
        #         "check if agent has attrib def and it's name is equivalent " \
        #         "to it's corresponding schema key name"
        #     attrDef = matchedAttrDefs[0]
        #     schema = await self.issuer.genSchema(schemaKey.name,
        #                                          schemaKey.version,
        #                                          attrDef.attribNames(),
        #                                          'CL')
        #     if schema:
        #         schemaId = ID(schemaKey=schema.getKey(), schemaId=schema.seqId)
        #         p_prime, q_prime = primes["prime2"]
        #         await self.issuer.genKeys(schemaId, p_prime=p_prime, q_prime=q_prime)
        #         await self.issuer.issueAccumulator(schemaId=schemaId, iA='110', L=5)
        #
        # await self.initAvailableClaimList()

    async def bootstrap(self):
        await runBootstrap(self.add_schemas_to_wallet)


